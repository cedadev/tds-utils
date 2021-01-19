from netCDF4 import Dataset

from tds_utils.aggregation.exceptions import CoordinatesError


class BaseDatasetReader(object):
    """
    Class to encapsulate opening a dataset and reading coordinate values from
    it
    """

    def __init__(self, filename):
        self.filename = filename

    def __enter__(self):
        """
        Open the file or perform other setup tasks
        """
        raise NotImplementedError

    def __exit__(self, *args, **kwargs):
        """
        Close files or perform other cleanup tasks
        """
        raise NotImplementedError

    def get_coord_values(self, dimension):
        """
        Return (units, values) where `units` are the units for the given
        dimension in the dataset, and `values` is a list of coordinate values
        sorted in ascending order.

        This method should raise CoordinatesError on error.
        """
        raise NotImplementedError

    def get_attribute(self, attr):
        """
        Read and return a global attribute from the dataset
        """
        raise NotImplementedError


class NetcdfDatasetReader(BaseDatasetReader):
    """
    Dataset reader that reads NetCDF files
    """
    def __enter__(self):
        self.ds = Dataset(self.filename)
        return self

    def __exit__(self, *args, **kwargs):
        self.ds.close()

    def get_coord_values(self, dimension):
        try:
            var = self.ds.variables[dimension]
        except KeyError:
            raise CoordinatesError("Variable '{}' not found in file '{}'"
                                   .format(dimension, self.filename))

        # Aggregation dimension should be one-dimensional
        if len(var.shape) != 1:
            raise CoordinatesError(
                "Aggregation dimension must be one-dimensional - shape is {} "
                "in file '{}'" .format(var.shape, self.filename)
            )

        values = sorted(var)
        try:
            units = var.units
        except AttributeError:
            units = None
        return units, values

    def get_attribute(self, attr):
        return getattr(self.ds, attr)
