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
