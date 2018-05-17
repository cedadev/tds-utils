import os
import xml.etree.cElementTree as ET
import json

import pytest
from netCDF4 import Dataset
import numpy as np

from tds_utils.find_ncml import find_ncml_references
from tds_utils.find_netcdf import find_netcdf_references
from tds_utils.xml_utils import element_to_string
from tds_utils.aggregate import create_aggregation, AggregationError
from tds_utils.partition_files import partition_files
from tds_utils.cache_remote_aggregations import AggregationCacher


class TestAggregationCreation(object):

    def netcdf_file(self, tmpdir, filename):
        """
        Create a NetCDF file containing just a time dimension with a single
        value. Return the path at which the dataset is saved.
        """
        path = str(tmpdir.join(filename))
        ds = Dataset(path, "w")
        ds.createDimension("time", None)
        time_var = ds.createVariable("time", np.float32, ("time",))
        time_var[:] = [1234]
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

        for filename, units in diff_files + same_files:
            path = tmpdir.join(filename)
            ds = Dataset(path, "w")
            ds.createDimension("time", None)
            time_var = ds.createVariable("time", np.float32, ("time",))
            time_var.units = units
            time_var[:] = [0]
            ds.close()

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

        try:
            _parsed_el = ET.fromstring(xml)
        except ET.ParseError:
            assert False, "element_to_string() returned malformed XML"

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
        files = [self.netcdf_file(tmpdir, filename) for filename in filenames]

        agg = create_aggregation(files, "time", cache=True)
        agg_el = list(agg)[0]
        netcdf_els = agg_el.findall("netcdf")

        assert len(netcdf_els) == n

        for i, el in enumerate(netcdf_els):
            assert "location" in el.attrib
            assert "coordValue" in el.attrib
            assert el.attrib["location"].endswith(filenames[i])
            assert el.attrib["coordValue"] == "1234.0"

    def test_file_order(self, tmpdir):
        """
        Test that the file list in the NcML aggregation is sorted in time order
        when cache=True, and in the order given otherwise
        """
        f1 = self.netcdf_file(tmpdir, "ds_1.nc")
        f2 = self.netcdf_file(tmpdir, "ds_2.nc")
        ds1 = Dataset(f1, "a")
        ds2 = Dataset(f2, "a")

        ds1.variables["time"][:] = 300
        ds2.variables["time"][:] = 10

        ds1.close()
        ds2.close()

        # Give file list in reverse order - result should be sorted
        agg = create_aggregation([f1, f2], "time", cache=True)
        found_files = [el.attrib["location"] for el in list(agg)[0].findall("netcdf")]
        assert found_files == [f2, f1]

        # Don't cache coordinate values - should stay in the wrong order
        agg2 = create_aggregation([f1, f2], "time", cache=False)
        found_files2 = [el.attrib["location"] for el in list(agg2)[0].findall("netcdf")]
        assert found_files2 == [f1, f2]

    def test_error_when_multiple_time_values(self, tmpdir):
        """
        Check that an error is raised when trying to process a file that
        contains more than one time coordinate value
        """
        f = self.netcdf_file(tmpdir, "ds.nc")
        ds = Dataset(f, "a")
        ds.variables["time"][:] = [1, 2, 3, 4, 5]
        ds.close()
        assert pytest.raises(AggregationError, create_aggregation, [f], "time",
                             cache=True)

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
