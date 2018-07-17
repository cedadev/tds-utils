import os
import xml.etree.cElementTree as ET
import json
from time import time
from collections import OrderedDict

import pytest
from netCDF4 import Dataset
import numpy as np

from tds_utils.find_ncml import find_ncml_references
from tds_utils.find_netcdf import find_netcdf_references
from tds_utils.xml_utils import element_to_string
from tds_utils.aggregation import (create_aggregation, AggregationError,
                                   OverlappingUnitsError, BaseAggregationCreator,
                                   BaseDatasetReader, AggregationType,
                                   NcMLVariable)
from tds_utils.partition_files import partition_files
from tds_utils.cache_remote_aggregations import AggregationCacher
from tds_utils.create_catalog import get_catalog_name, CatalogBuilder


def assert_valid_xml(xml_string):
    """
    Aassert a string is valid XML
    """
    try:
        _parsed_el = ET.fromstring(xml_string)
    except ET.ParseError:
        assert False, "Invalid XML"


class TestAggregationCreation(object):

    def netcdf_file(self, tmpdir, filename, dim="time", values=[1234],
                    units=None):
        """
        Create a NetCDF file containing a single dimension. Return the path
        at which the dataset is saved.
        """
        path = str(tmpdir.join(filename))
        ds = Dataset(path, "w")
        ds.createDimension(dim, None)
        var = ds.createVariable(dim, np.float32, (dim,))
        if units:
            var.units = units
        var[:] = values
        ds.close()
        return path

    def test_different_time_units(self, tmpdir):
        """
        Check that the 'timeUnitsChange' attribute is present on the
        aggregation when files have different time units and time coordinates
        are cached
        """
        diff_files = [
            ("diff_units_1.nc", "days since 1970-01-01 00:00:00 UTC"),
            ("diff_units_2.nc", "days since 1970-01-02 00:00:00 UTC"),
            ("diff_units_3.nc", "days since 1970-01-03 00:00:00 UTC")
        ]
        same_files = [
            ("same_units_1.nc", "days since 1973-01-03 00:00:00 UTC"),
            ("same_units_2.nc", "days since 1973-01-03 00:00:00 UTC"),
            ("same_units_3.nc", "days since 1973-01-03 00:00:00 UTC")
        ]

        for filename, units in diff_files:
            self.netcdf_file(tmpdir, filename, units=units)
        for i, (filename, units) in enumerate(same_files):
            self.netcdf_file(tmpdir, filename, units=units, values=[i])

        # timeUnitsChange should be present in the aggregation with different
        # time units...
        diff_agg = create_aggregation([tmpdir.join(fname) for fname, _ in diff_files],
                                      "time", cache=True)
        diff_agg_el = list(diff_agg)[0]
        assert "timeUnitsChange" in diff_agg_el.attrib
        assert diff_agg_el.attrib["timeUnitsChange"] == "true"

        # ...but not present otherwise
        same_agg = create_aggregation([tmpdir.join(fname) for fname, _ in same_files],
                                      "time", cache=True)
        same_agg_el = list(same_agg)[0]
        assert "timeUnitsChange" not in same_agg_el.attrib

        # Check coordValue is not present for the different units aggregation
        netcdf_els = diff_agg_el.findall("netcdf")
        assert len(netcdf_els) > 1
        for el in netcdf_els:
            assert "coordValue" not in el.attrib

    def test_xml_to_string(self):
        """
        Test that the method to convert an ET.Element instance to a string
        produces valid XML with correct indentation
        """
        el = ET.Element("parent", myattr="myval")
        ET.SubElement(el, "child", childattr="childval")
        ET.SubElement(el, "child")
        with_text = ET.SubElement(el, "anotherelement", attr="value")
        with_text.text = "hello"
        xml = element_to_string(el)

        assert_valid_xml(xml)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<parent myattr="myval">',
            '  <child childattr="childval"/>',
            '  <child/>',
            '  <anotherelement attr="value">',
            '    hello',
            '  </anotherelement>',
            '</parent>'
        ]
        assert xml == os.linesep.join(lines)

    def test_aggregation(self, tmpdir):
        """
        Test that the method to create an NcML aggregation includes references
        to the all the input files and the expected attributes are present
        with correct values
        """
        n = 5
        filenames = ["ds_{}.nc".format(i) for i in range(n)]
        coord_values = list(range(n))
        files = [self.netcdf_file(tmpdir, filename, values=[val])
                 for filename, val in zip(filenames, coord_values)]

        agg = create_aggregation(files, "time", cache=True)
        agg_el = list(agg)[0]
        netcdf_els = agg_el.findall("netcdf")

        assert len(netcdf_els) == n

        for i, (el, expected_value) in enumerate(zip(netcdf_els, coord_values)):
            assert "location" in el.attrib
            assert "coordValue" in el.attrib
            assert el.attrib["location"].endswith(filenames[i])
            assert el.attrib["coordValue"] == str(float(expected_value))

    def test_multiple_coord_vaules(self, tmpdir):
        f = self.netcdf_file(tmpdir, "f", values=[1, 2, 3])
        agg = create_aggregation([f], "time", cache=True)
        agg_el = list(agg)[0]
        netcdf_els = agg_el.findall("netcdf")
        assert len(netcdf_els) == 1
        assert netcdf_els[0].attrib["coordValue"] == "1.0,2.0,3.0"

    def test_file_order(self, tmpdir):
        """
        Test that the file list in the NcML aggregation is sorted in time order
        when cache=True, and in the order given otherwise
        """
        f1 = self.netcdf_file(tmpdir, "ds_1.nc", values=[300])
        f2 = self.netcdf_file(tmpdir, "ds_2.nc", values=[10])

        # Give file list in reverse order - result should be sorted
        agg = create_aggregation([f1, f2], "time", cache=True)
        found_files = [el.attrib["location"] for el in list(agg)[0].findall("netcdf")]
        assert found_files == [f2, f1]

        # Don't cache coordinate values - should stay in the wrong order
        agg2 = create_aggregation([f1, f2], "time", cache=False)
        found_files2 = [el.attrib["location"] for el in list(agg2)[0].findall("netcdf")]
        assert found_files2 == [f1, f2]

    def test_multiple_time_values_sorting(self, tmpdir):
        """
        Check that files are sorted correctly when they have multiple time
        values
        """
        def get_sorted(*args):
            suffix = "{}.nc".format(time())
            filenames = []
            for i, (filename, val) in enumerate(args):
                filenames.append(self.netcdf_file(tmpdir, filename, values=val))

            agg = create_aggregation(filenames, "time", cache=True)
            return [os.path.basename(el.attrib["location"])
                    for el in list(agg)[0].findall("netcdf")]

        # Simple cases
        assert get_sorted(("f1", [10]), ("f2", [20, 30])) == ["f1", "f2"]
        assert get_sorted(("f3", [10, 50]), ("f4", [5])) == ["f4", "f3"]

        # Both files with multiple time values
        assert get_sorted(("f5", [6, 7, 8]), ("f6", [1, 2, 3])) == ["f6", "f5"]
        assert get_sorted(("f7", [6, 7, 8, 100]), ("f8", [101, 102])) == ["f7", "f8"]

        # More than two files
        got = get_sorted(("f9", [10, 11, 12]), ("f10", [20, 21, 22]),
                         ("f11", [5, 6, 7]))
        assert got == ["f11", "f9", "f10"]

    def test_overlapping_time_values(self, tmpdir):
        """
        Check that an error is raised when files have overlapping time values
        and cache=True
        """
        def do_test(*values):
            suffix = "{}.nc".format(time())
            filenames = []
            for i, val in enumerate(values):
                filename = "f{}_{}".format(i, suffix)
                filenames.append(self.netcdf_file(tmpdir, filename, values=val))

            with pytest.raises(OverlappingUnitsError):
                create_aggregation(filenames, "time", cache=True)

        # Test when one time range is fully contained within the other
        do_test([10, 20, 30], [15, 16])
        # when ranges overlap but not entirely
        do_test([10, 20, 30], [5, 15])
        # when time values are repeated
        do_test([10], [10])
        do_test([10, 20], [20, 21])
        # more than two ranges
        do_test([10, 20], [30, 40], [25, 60])

    def test_no_caching(self, tmpdir):
        """
        Check that files are not opened if cache=False when creating an
        aggregation
        """
        f = self.netcdf_file(tmpdir, "ds.nc")
        try:
            create_aggregation([f], "nonexistantdimension", cache=False)
        except AggregationError as ex:
            assert False, "Unexpected error: {}".format(ex)

    def test_some_files_fail(self, tmpdir):
        """
        Check that an aggregation is still created if some (but not all) files
        are invalid
        """
        no_time = self.netcdf_file(tmpdir, "no-time.nc", dim="not-time")
        time = self.netcdf_file(tmpdir, "time.nc", dim="time")
        try:
            agg = create_aggregation([no_time, time], "time", cache=True)
            found_files = [el.attrib["location"]
                           for el in list(agg)[0].findall("netcdf")]
            assert found_files == [time]
        except AggregationError as ex:
            assert False, "Unexpected error: {}".format(ex)

    def test_all_files_fail(self, tmpdir):
        """
        Check an exception is thrown if all files are invalid
        """
        no_time = self.netcdf_file(tmpdir, "no-time.nc", dim="not-time")
        no_time2 = self.netcdf_file(tmpdir, "no-time2.nc", dim="not-time")
        with pytest.raises(AggregationError):
            create_aggregation([no_time, no_time2], "time", cache=True)

    def test_custom_agg_creator_cls(self, tmpdir):
        class CustomReaderClass(BaseDatasetReader):
            def __enter__(self):
                self.f = open(self.filename)
                return self

            def __exit__(self, *args, **kwargs):
                self.f.close()

            def get_coord_values(self, dimension):
                val = float(self.f.read().strip())
                return ("some cool units", [val])

        class CustomAggTypeCreator(BaseAggregationCreator):
            aggregation_type = AggregationType.JOIN_NEW
            dataset_reader_cls = CustomReaderClass
            extra_variables = [
                NcMLVariable(name="test-var", shape="time", type="int",
                             attrs={"units": "seconds since the big bang"})
                ]

            def process_root_element(self, root):
                ET.SubElement(root, "someextraelement")
                return root

        c = CustomAggTypeCreator("time")

        f1 = tmpdir.join("f1")
        f2 = tmpdir.join("f2")
        f1.write("135.1")
        f2.write("235.2")

        agg = c.create_aggregation(map(str, [f1, f2]), cache=True)
        agg_el = agg.findall("aggregation")[0]
        assert "type" in agg_el.attrib
        assert agg_el.attrib["type"] == "joinNew"

        coord_vals = [el.attrib["coordValue"] for el in agg_el.findall("netcdf")]
        assert coord_vals == ["135.1", "235.2"]

        # Check extra variables are present
        extra_vars = agg.findall("variable")
        assert len(extra_vars) == 1
        var = extra_vars[0]
        assert var.attrib == {"name": "test-var", "shape": "time",
                              "type": "int"}
        var_attributes = var.findall("attribute")
        assert len(var_attributes) == 1
        expected_attrib = {"name": "units",
                           "value": "seconds since the big bang"}
        assert var_attributes[0].attrib == expected_attrib

        # Check extra processing was performed
        assert len(agg.findall("someextraelement")) == 1

    def test_global_attributes(self, tmpdir):
        nc = self.netcdf_file(tmpdir, "f.nc")
        global_attrs = OrderedDict()
        global_attrs["myattr"] = "myvalue"
        global_attrs["otherattr"] = "hello"
        root = create_aggregation([str(nc)], "time",
                                  global_attrs=global_attrs)
        print(ET.dump(root))
        attribute_els = root.findall("attribute")
        assert len(attribute_els) == 2
        assert attribute_els[1].attrib == {"name": "myattr", "value": "myvalue"}
        assert attribute_els[0].attrib == {"name": "otherattr", "value": "hello"}


class TestPartitioning(object):
    def test_partition(self):
        """
        Test the algorithm to detect dates in file paths and partition a list
        into groups
        """
        all_files = [
            "/path/one/2018/01/01/f1.nc",
            "/path/one/2018/01/02/f2.nc",
            "/path/two/2019/01/01/f3.nc",
            # Paths only differ by digits but one of the changes is version
            # number - check they get split into two
            "/path/three/v1/2009/01/01/f4.nc",
            "/path/three/v1/2008/01/01/f5.nc",
            "/path/three/v2/2009/01/01/f6.nc",
            # Same as above but with no alphabetic characters in version
            "/path/four/1.0/2007/01/01/f7.nc",
            "/path/four/1.0/2003/01/01/f8.nc",
            "/path/four/2.0/2007/01/01/f9.nc"
        ]

        expected_part = {
            "/path/one/xxxx/xx/xx": [
                "/path/one/2018/01/01/f1.nc",
                "/path/one/2018/01/02/f2.nc"
            ],
            "/path/two/xxxx/xx/xx": ["/path/two/2019/01/01/f3.nc"],

            "/path/three/v1/xxxx/xx/xx": [
                "/path/three/v1/2009/01/01/f4.nc",
                "/path/three/v1/2008/01/01/f5.nc"
            ],

            "/path/three/v2/xxxx/xx/xx": ["/path/three/v2/2009/01/01/f6.nc"],

            "/path/four/1.0/xxxx/xx/xx": [
                "/path/four/1.0/2007/01/01/f7.nc",
                "/path/four/1.0/2003/01/01/f8.nc"
            ],

            "/path/four/2.0/xxxx/xx/xx": ["/path/four/2.0/2007/01/01/f9.nc"]
        }
        assert partition_files(all_files) == expected_part


class TestAggregationCaching(object):
    def test_get_agg_url(self, tmpdir):
        json_file = tmpdir.join("ds.json")
        json_file.write(json.dumps({
            "opendap-dataset": {
                "generate_aggregation": True,
                "include_in_wms": False,
                "extra_stuff_should_be_ignore": "yep"
            },
            "wms-dataset": {
                "generate_aggregation": True,
                "include_in_wms": True,
            },
            "no-aggregation-dataset": {
                "generate_aggregation": False,
                "include_in_wms": False,
            },
        }))

        ac = AggregationCacher(str(json_file), "http://server")
        expected = [
            "http://server/dodsC/opendap-dataset.dds",
            "http://server/wms/wms-dataset?service=WMS&version=1.3.0&request=GetCapabilities"
        ]
        assert set(ac.get_all_urls()) == set(expected)


class TestNcmlFinder(object):
    def test_no_ncml(self, tmpdir):
        """
        Check that no paths are returned if no NcML files are referenced in the
        XML
        """
        catalog = tmpdir.join("catalog.xml")
        catalog.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog>
                <dataset name="some.dataset" ID="some.dataset">
                </dataset>
            </catalog>
        """.strip())
        got = list(find_ncml_references(str(catalog)))
        assert got == []

    def test_ncml_present(self, tmpdir):
        """
        Check paths are returned when expected
        """
        catalog = tmpdir.join("catalog.xml")
        catalog.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog xmlns="some-namespace1">
                <dataset name="some.dataset" ID="some.dataset">
                    <dataset>
                        <netcdf location="/my/ncml/aggregation.ncml"/>
                    </dataset>
                    <dataset>
                        <netcdf xmlns="some-namespace2"
                                location="/my/other/aggregation.ncml"/>
                    </dataset>
                </dataset>
            </catalog>
        """.strip())
        expected = ["/my/ncml/aggregation.ncml", "/my/other/aggregation.ncml"]
        got = list(find_ncml_references(str(catalog)))
        assert got == expected

    def test_non_netcdf_element(self, tmpdir):
        """
        Check that other elements with a 'location' attribute are not also
        included
        """
        catalog = tmpdir.join("catalog.xml")
        catalog.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog>
                <dataset name="some.dataset" ID="some.dataset">
                    <dataset><somethingelsenetcdf location="/not/an/aggregation"/></dataset>
                    <dataset><netcdfsomethingelse location="/also/not/an/aggregation"/></dataset>
                </dataset>
            </catalog>
        """.strip())
        got = list(find_ncml_references(str(catalog)))
        assert got == []


class TestNetcdfFinder(object):
    def test_netcdf_present(self, tmpdir):
        """
        Check that a NetCDF file is found and the dataset roots are replaced
        with path on disk
        """
        catalog = tmpdir.join("catalog.xml")
        catalog.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog>
                <dataset name="some.dataset1" ID="some.dataset1" urlPath="prefix1/one.nc"/>
                <dataset name="some.dataset2" ID="some.dataset2" urlPath="prefix2/two.nc"/>
                <dataset name="some.dataset3" ID="some.dataset3" urlPath="prefix3/three.nc"/>
                <dataset name="some.dataset4" ID="some.dataset4">
                    <dataset name="nested.dataset" ID="nested.dataset" urlPath="nested.nc"/>
                </dataset>
            </catalog>
        """.strip())
        roots = {
            "prefix1": "/first/path",
            "prefix2": "/second/path"
        }
        got = list(find_netcdf_references(str(catalog), dataset_roots=roots))
        assert got == ["/first/path/one.nc", "/second/path/two.nc",
                       "prefix3/three.nc", "nested.nc"]


class TestCreateCatalog(object):
    def test_get_catalog_name(self, tmpdir):
        with_name = tmpdir.join("catalog-with-a-name.xml")
        with_name.write("""
            <?xml version="1.0" encoding="UTF-8"?>
            <catalog name="some-name">
                <dataset/>
            </catalog>
        """.strip())

        no_name1 = tmpdir.join("catalog-without-a-name.xml")
        no_name2 = tmpdir.join("catalog-with-no-name")
        for cat in (no_name1, no_name2):
            cat.write("""
                <?xml version="1.0" encoding="UTF-8"?>
                <catalog>
                    <dataset/>
                </catalog>
            """.strip())

        assert get_catalog_name(str(with_name)) == "some-name"
        assert get_catalog_name(str(no_name1)) == "catalog-without-a-name"
        assert get_catalog_name(str(no_name2)) == "catalog-with-no-name"

    def test_root_catalog(self, tmpdir):
        filenames = ("one.xml", "two.xml", "three.xml")
        catalogs = list(map(tmpdir.join, filenames))
        for name, cat in zip(filenames, catalogs):
            cat.write("""
                <?xml version="1.0" encoding="UTF-8"?>
                <catalog name="{name}">
                    <dataset/>
                </catalog>
            """.strip().format(name=name))

        # Pass in absolute paths
        paths = list(map(str, catalogs))
        root_catalog = CatalogBuilder().root_catalog(paths, str(tmpdir))
        assert_valid_xml(root_catalog)
        assert "<catalogRef" in root_catalog
        # Check that paths are relative in the generated catalog
        for name in filenames:
            assert name in root_catalog

    def test_basic_dataset_catalog(self):
        files = ("aerosol.nc", "soil_moisture.nc")
        ds_id = "my-really-cool-dataset"
        catalog = CatalogBuilder().dataset_catalog(files, ds_id)
        assert_valid_xml(catalog)
        assert ds_id in catalog
        for f in files:
            assert f in catalog

    def test_access_methods(self, tmpdir):
        def get_services(xml):
            """
            Return a set containing all service types found in the given
            catalog
            """
            root = ET.fromstring(xml)
            services_els = [el for el in root.iter() if el.tag.endswith("service")]
            services = set([])
            for s in services_els:
                services.add(s.attrib["serviceType"])
            return services

        b = CatalogBuilder()

        # Try all combinations of opendap and ncml and check services listed
        # are correct
        just_http = set(["HTTPServer"])
        http_and_opendap = set(["HTTPServer", "OpenDAP"])

        catalog1 = b.dataset_catalog(["file.nc"], "id", opendap=False)
        assert get_services(catalog1) == just_http

        catalog2 = b.dataset_catalog(["file.nc"], "id", opendap=True)
        assert get_services(catalog2) == http_and_opendap

        catalog3 = b.dataset_catalog(["file.nc"], "id", opendap=False,
                                     ncml_path="ncml")
        assert get_services(catalog3) == http_and_opendap

        catalog4 = b.dataset_catalog(["file.nc"], "id", opendap=True,
                                     ncml_path="ncml")
        assert get_services(catalog4) == http_and_opendap

    def test_aggregation(self):
        b = CatalogBuilder()
        ncml_path = "/path/to/agg.ncml"
        with_ncml = b.dataset_catalog(["file.nc"], "id",
                                      ncml_path=ncml_path)
        without_ncml = b.dataset_catalog(["file.nc"], "id")
        assert "<netcdf" in with_ncml
        assert "<netcdf" not in without_ncml
        assert ncml_path in with_ncml
