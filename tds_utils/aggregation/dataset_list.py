import sys
import bisect
from collections import namedtuple

from tds_utils.aggregation.exceptions import (CoordinatesError,
                                              OverlappingUnitsError)


class AggregatedGlobalAttr:
    """
    Class to represent a global variable whose value should be calculated using
    values of the attribute in each dataset
    """
    def __init__(self, attr, callback):
        """
        `attr` is the attribute name, and `callback` is a function that takes
        a list of attribute values and returns the one that should be used in
        the aggregation
        """
        self.attr = attr
        self.callback = callback
        self.values = []

    def add_value(self, value):
        self.values.append(value)

    def get_value(self):
        if not self.values:
            raise ValueError(
                "Attribute '{}' not found in any files".format(self.attr)
            )
        return self.callback(self.values)


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

    def __init__(self, dimension, ds_reader_cls, attr_aggs=None):
        self.dimension = dimension
        self.ds_reader_cls = ds_reader_cls
        self.attr_aggs = attr_aggs or []

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
        # so do not bother to open file (unless need to read attributes)
        if not self.attr_aggs and self.multiple_units:
            self.append((None, filename))
            return

        with self.ds_reader_cls(filename) as ds:
            try:
                units, values = ds.get_coord_values(self.dimension)
            except CoordinatesError as ex:
                print("WARNING: {}".format(ex), file=sys.stderr)
                return

            # Update attribute aggregation values
            for attr_agg in self.attr_aggs:
                try:
                    attr_value = ds.get_attribute(attr_agg.attr)
                except AttributeError:
                    print("WARNING: Attribute '{}' not found in '{}'"
                          .format(attr_agg.attr, filename),
                          file=sys.stderr)
                    continue
                attr_agg.add_value(attr_value)

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
