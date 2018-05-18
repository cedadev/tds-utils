"""
Create a THREDDS catalog from a list of NetCDF files
"""
import sys
import os
import argparse
from enum import Enum
from collections import namedtuple as nt

from jinja2 import Environment, PackageLoader


# Classes corresponding to various elements that make up the catalog
ThreddsService = nt("ThreddsService", ["name", "type", "base"])
AccessMethod = nt("AccessMethod", ["service", "url_path", "data_format"])
Aggregation = nt("Aggregation", ["ncml_path", "access_methods"])
DatasetRoot = nt("DatasetRoot", ["location", "path"])
ThreddsDataset = nt("ThreddsDataset", ["name", "id", "access_methods"])


class AvailableServices(Enum):
    """
    Enumeration of the available service types
    """
    HTTP = ThreddsService(name="http", type="HTTPServer", base="fileServer")
    OPENDAP = ThreddsService(name="opendap", type="OpenDAP", base="dodsC")


def get_catalog(filenames, ds_id, opendap=False, ncml_path=None):
    """
    Build a THREDDS catalog and return the XML as a string
    """
    # Work out which services are required
    file_services = set([AvailableServices.HTTP.value])
    if opendap:
        file_services.add(AvailableServices.OPENDAP.value)
    aggregation_services = set([AvailableServices.OPENDAP.value])
    all_services = file_services.copy()
    if ncml_path:
        all_services.add(AvailableServices.OPENDAP.value)

    # An absolute path as urlPath does not work, so need to use a datasetRoot
    ds_root = DatasetRoot(path="{}_root".format(ds_id), location="/")

    datasets = []
    for filename in filenames:
        this_id = os.path.basename(filename)
        url_path = ds_root.path + os.path.abspath(filename)
        a_meths = [AccessMethod(s, url_path, "NetCDF-4") for s in file_services]
        datasets.append(ThreddsDataset(name=this_id, id=this_id,
                                       access_methods=a_meths))

    aggregation = None
    if ncml_path:
        # url path is arbitrary here
        url_path = os.path.basename(ncml_path)
        a_meths = [AccessMethod(s, url_path, "NcML") for s in aggregation_services]
        aggregation = Aggregation(ncml_path, a_meths)

    context = {
        "services": all_services,
        "dataset_roots": [ds_root],
        "dataset_id": ds_id,
        "datasets": datasets,
        "aggregation": aggregation,
    }

    env = Environment(loader=PackageLoader("tds_utils", "templates"))
    env.trim_blocks = True
    env.lstrip_blocks = True
    template = env.get_template("dataset_catalog.xml")
    return template.render(**context)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-f", "--files",
        type=argparse.FileType("r"),
        required=True,
        help="File containing list of NetCDF files, or - to read stdin"
    )
    parser.add_argument(
        "-i", "--ds-id",
        required=True,
        help="Dataset ID"
    )
    parser.add_argument(
        "-o", "--opendap",
        action="store_true",
        default=False,
        help="Make individual files available through OPeNDAP "
             "[deafult: %(default)s]"
    )
    parser.add_argument(
        "-n", "--ncml",
        nargs="?",
        help="Path to NcML file to create an aggregation"
    )
    args = parser.parse_args(sys.argv[1:])

    filenames = [line.strip() for line in args.files.readlines() if line]
    print(get_catalog(filenames, args.ds_id, opendap=args.opendap,
                      ncml_path=args.ncml))
