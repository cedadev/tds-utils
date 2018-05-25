import xml.etree.cElementTree as ET
from enum import Enum

from tds_utils.aggregation.dataset_list import DatasetList
from tds_utils.aggregation.readers import NetcdfDatasetReader
from tds_utils.aggregation.exceptions import AggregationError


class AggregationType(Enum):
    """
    Enumeration of allowed aggregation types, as defined by the NcML schema
    """
    JOIN_NEW = "joinNew"
    JOIN_EXISTING = "joinExisting"
    TILED = "tiled"
    UNION = "union"


class BaseAggregationCreator(object):
    """
    Class to encapsulate an aggregation type and a method of reading datasets.

    Child classes should define the properies documented below.
    """
    # Aggregation type -- see the AggregationType enum
    aggregation_type = None

    # Sub-class of BaseDatasetReader used to open and read datasets when
    # creating with cache=True. See BaseDatasetReader source code for usage
    dataset_reader_cls = None

    # NcML namespace
    ncml_xmlns = "http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2"

    def __init__(self, dimension):
        self.dimension = dimension

    def create_aggregation(self, file_list, cache=False):
        """
        Create an NcML aggregation for the filenames in `file_list` and return
        the root element as an instance of ET.Element.

        If `cache` is True then open each file to write the coordinate values in
        the NcML.
        """
        root = ET.Element("netcdf", xmlns=self.ncml_xmlns)
        aggregation = ET.SubElement(root, "aggregation",
                                    dimName=self.dimension,
                                    type=self.aggregation_type.value)

        # List of dicts containing attributes for <netcdf> sub-elements
        sub_el_attrs = []

        if cache:
            ds_list = DatasetList(self.dimension,
                                  ds_reader_cls=self.dataset_reader_cls)
            for filename in file_list:
                ds_list.add(filename)

            if not ds_list:
                raise AggregationError("No aggregation could be created")

            for filename, values in ds_list.datasets():
                attrs = {"location": filename}
                if not ds_list.multiple_units:
                    attrs["coordValue"] = ",".join(map(str, values))
                sub_el_attrs.append(attrs)

            if ds_list.multiple_units and self.dimension == "time":
                aggregation.attrib["timeUnitsChange"] = "true"

        # If not caching coordinate values then include in the order given
        else:
            sub_el_attrs = [{"location": filename} for filename in file_list]

        for attrs in sub_el_attrs:
            ET.SubElement(aggregation, "netcdf", **attrs)

        return root


class AggregationCreator(BaseAggregationCreator):
    """
    Default class to create joinExisting aggregations from NetCDF files
    """
    aggregation_type = AggregationType.JOIN_EXISTING
    dataset_reader_cls = NetcdfDatasetReader


def create_aggregation(file_list, agg_dimension, cache=False):
    """
    Convenience function to create an aggregation using the default class
    """
    return AggregationCreator(agg_dimension).create_aggregation(file_list,
                                                                cache)