"""
Read filenames of NetCDF datasets from standard input and print an NcML
aggregation to standard output.
"""
import os
import sys
import bisect
import xml.etree.cElementTree as ET
import argparse

from netCDF4 import Dataset

from tds_utils.xml_utils import element_to_string


class AggregationError(Exception):
    """
    An aggregation could not be created
    """


class CoordinatesError(Exception):
    """
    There is a problem with the coordinate variable in a NetCDF file
    """


class OverlappingUnitsError(Exception):
    """
    The coordinate values of files in the given list are overlapping
    """


class Interval(object):
    """
    Class representing an interval of floats that can be ordered based its
    lower bound
    """
    def __init__(self, values):
        self.values = values
        self.lower = values[0]
        self.upper = values[-1]

    def __lt__(self, x):
        return self.lower < x.lower


class DatasetList(list):
    """
    A list of datasets that can be sorted by their coordinate values
    """
    def __init__(self, dimension):
        self.dimension = dimension

        # Keep track of units seen in files added to the list, so that we can
        # tell if all files have the same units or not
        self.found_units = set([])
        self.multiple_units = False

        super().__init__(self)

    def add(self, filename):
        """
        Add a file (and its coordinate values) to the list
        """
        # If already know there are multiple units, sort order does not matter
        if self.multiple_units:
            self.append((None, filename))
            return

        try:
            units, values = DatasetList.get_coord_values(filename,
                                                         self.dimension)
        except CoordinatesError as ex:
            print("WARNING: {}".format(ex), file=sys.stderr)
            return

        # Check if we have seen these units before
        self.found_units.add(units)
        if len(self.found_units) > 1:
            self.multiple_units = True
            self.add(filename)
            return

        interval = Interval(values)
        # Sort by interval but keep track of filename too
        key = (interval, filename)
        # Get index to insert at to preserve sort order
        idx = bisect.bisect(self, key)
        self.insert(idx, key)

        # Check that this interval does not overlap with the previous or
        # next ones
        before = None
        after = None
        if idx > 0:
            before = self[idx - 1][0]
        if idx < len(self) - 1:
            after = self[idx + 1][0]

        if ((before and interval.lower <= before.upper) or
                (after and interval.upper >= after.lower)):
            raise OverlappingUnitsError("File list has overlapping coordinate "
                                        "values")

    def datasets(self):
        """
        Return a generator yielding (filename, coordinate_values), or
        (filename, None) if multiple units were found and values were not
        stored
        """
        for interval, filename in self:
            if interval:
                yield filename, interval.values
            else:
                yield filename, None

    @classmethod
    def get_coord_values(cls, filename, dimension):
        """
        Return (units, values) of the coordinate variable for the given
        dimension in a NetCDF file. `values` is a list sorted in ascending
        order.
        """
        ds = Dataset(filename)
        try:
            var = ds.variables[dimension]
        except KeyError:
            raise CoordinatesError("Variable '{}' not found in file '{}'"
                                   .format(dimension, filename))

        # Aggregation dimension should be one-dimensional
        if len(var.shape) != 1:
            raise CoordinatesError(
                "Aggregation dimension must be one-dimensional - shape is {} "
                "in file '{}'" .format(var.shape, filename)
            )

        values = sorted(var)
        try:
            units = var.units
        except AttributeError:
            units = None
        ds.close()
        return (units, values)


def create_aggregation(file_list, agg_dimension, cache=False):
    """
    Create a 'joinExisting' NcML aggregation for the filenames in `file_list`
    and return the root element as an instance of ET.Element.

    If `cache` is True then open each file to write the coordinate values in
    the NcML.
    """
    root = ET.Element("netcdf", xmlns="http://www.unidata.ucar.edu/namespaces/netcdf/ncml-2.2")
    aggregation = ET.SubElement(root, "aggregation", dimName=agg_dimension,
                                type="joinExisting")

    # List of dicts containing attributes for <netcdf> sub-elements
    sub_el_attrs = []

    if cache:
        ds_list = DatasetList(agg_dimension)
        for filename in file_list:
            ds_list.add(filename)

        if not ds_list:
            raise AggregationError("No aggregation could be created")

        for filename, values in ds_list.datasets():
            attrs = {"location": filename}
            if not ds_list.multiple_units:
                attrs["coordValue"] = ",".join(map(str, values))
            sub_el_attrs.append(attrs)

        if ds_list.multiple_units and agg_dimension == "time":
            aggregation.attrib["timeUnitsChange"] = "true"

    # If not caching coordinate values then include in the order given
    else:
        sub_el_attrs = [{"location": filename} for filename in file_list]

    for attrs in sub_el_attrs:
        ET.SubElement(aggregation, "netcdf", **attrs)
    return root


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-d", "--dimension",
        default="time",
        help="The dimension along which to aggregate [default: %(default)s]"
    )
    parser.add_argument(
        "-c", "--cache",
        action="store_true",
        default=False,
        help="Open NetCDF files to read coordinate values to include in the "
             "NcML. This caches the values so that TDS does not need to open "
             "each file when accessing the aggregation [default: %(default)s]"
    )

    args = parser.parse_args(sys.argv[1:])

    path_list = [line for line in sys.stdin.read().split(os.linesep) if line]
    ncml_el = create_aggregation(path_list, args.dimension, cache=args.cache)
    print(element_to_string(ncml_el))
