"""
Create a THREDDS catalog from a list of NetCDF files. Can create either dataset
catalogs or root-level catalogs with links to other catalogs.
"""
import sys
import os
import argparse
from enum import Enum
from collections import namedtuple as nt
from xml.etree import cElementTree as ET

from jinja2 import Environment, PackageLoader


# Classes corresponding to various elements that make up the catalog
CatalogRef = nt("CatalogRef", ["name", "title", "href"])
ThreddsService = nt("ThreddsService", ["name", "type", "base"])
AccessMethod = nt("AccessMethod", ["service", "url_path", "data_format"])

# Note: in theory an aggregation shouldn't have a URL path as the path could
# be different for different access methods. In practise THREDDS seems to
# require the containing <dataset> to have a urlPath attribute for
# aggregations, and it must match the urlPath for each access method (this is
# surely a bug in THREDDS)
Aggregation = nt("Aggregation", ["ncml_path", "access_methods", "url_path"])

DatasetRoot = nt("DatasetRoot", ["location", "path"])
ThreddsDataset = nt("ThreddsDataset", ["name", "id", "access_methods"])


class AvailableServices(Enum):
    """
    Enumeration of the available service types
    """
    HTTP = ThreddsService(name="http", type="HTTPServer", base="fileServer")
    OPENDAP = ThreddsService(name="opendap", type="OpenDAP", base="dodsC")


def get_catalog_name(filename):
    """
    Parse a catalog and return its name
    """
    tree = ET.ElementTree()
    try:
        tree.parse(filename)
    except ET.ParseError:
        raise ValueError("File '{}' is not a valid XML document"
                         .format(filename))
    root = tree.getroot()

    try:
        return root.attrib["name"]
    except KeyError:
        # Make up a name based on filename if catalog has no 'name' attribute
        basename = os.path.basename(filename)
        if basename.endswith(".xml"):
            return basename[:-4]
        return basename


class CatalogBuilder(object):

    def __init__(self):
        self.env = Environment(loader=PackageLoader("tds_utils", "templates"))
        self.env.trim_blocks = True
        self.env.lstrip_blocks = True

    def render(self, template_name, **kwargs):
        """
        Render a template with the given context
        """
        template = self.env.get_template(template_name)
        return template.render(**kwargs)

    def create_dataset(self, filename, ds_root, file_services):
        this_id = os.path.basename(filename)
        url_path = ds_root.path + os.path.abspath(filename)
        a_meths = [AccessMethod(s, url_path, "NetCDF-4") for s in file_services]
        return ThreddsDataset(name=this_id, id=this_id, access_methods=a_meths)

    def dataset_catalog(self, filenames, ds_id, opendap=False, ncml_path=None):
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

        # An absolute path as urlPath does not work, so need to use a
        # datasetRoot
        ds_root = DatasetRoot(path="{}_root".format(ds_id), location="/")

        datasets = []
        for filename in filenames:
            ds = self.create_dataset(filename, ds_root, file_services)
            datasets.append(ds)

        aggregation = None
        if ncml_path:
            # url path is arbitrary here, but must be the same for each access
            # method (see note at Aggregation definition...)
            url_path = ds_id
            a_meths = [AccessMethod(s, url_path, "NcML")
                       for s in aggregation_services]
            aggregation = Aggregation(ncml_path, a_meths, url_path)

        context = {
            "services": all_services,
            "dataset_roots": [ds_root],
            "dataset_id": ds_id,
            "datasets": datasets,
            "aggregation": aggregation,
        }
        return self.render("dataset_catalog.xml", **context)

    def root_catalog(self, cat_paths, root_dir, name="THREDDS catalog"):
        """
        Build a root-level catalog that links to other catalogs, and return the
        XML as a string
        """
        catalogs = []
        for path in cat_paths:
            cat_name = get_catalog_name(path)
            # href must be relative to the root catalog itself
            href = os.path.relpath(os.path.abspath(path), start=root_dir)
            catalogs.append(CatalogRef(name=cat_name, title=cat_name,
                                       href=href))
        return self.render("root_catalog.xml", name=name, catalogs=catalogs)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(
        dest="type",
        metavar="TYPE",
        help="The type of catalog to create"
    )
    subparsers.required = True

    # Options for creating a dataset catalog
    dataset_cat_parser = subparsers.add_parser(
        "dataset",
        help="Create a catalog for a THREDDS dataset"
    )
    dataset_cat_parser.add_argument(
        "-f", "--files",
        type=argparse.FileType("r"),
        required=True,
        help="File containing list of NetCDF files, or - to read stdin"
    )
    dataset_cat_parser.add_argument(
        "-i", "--ds-id",
        required=True,
        help="ID for the new catalog"
    )
    dataset_cat_parser.add_argument(
        "-o", "--opendap",
        action="store_true",
        default=False,
        help="Make individual files available through OPeNDAP "
             "[deafult: %(default)s]"
    )
    dataset_cat_parser.add_argument(
        "-n", "--ncml",
        nargs="?",
        help="Path to NcML file to create an aggregation"
    )

    # Options for root level catalog
    root_cat_parser = subparsers.add_parser(
        "root",
        help="Create a root level catalog that links to dataset catalogs"
    )
    root_cat_parser.add_argument(
        "-c", "--catalogs",
        type=argparse.FileType("r"),
        required=True,
        help="File containing list of catalog paths, or - to read stdin"
    )
    root_cat_parser.add_argument(
        "-r", "--root-dir",
        required=True,
        help="The directory in which the root catalog will be written. This "
             "is needed because THREDDS requires relative paths for linking "
             "to other catalogs"
    )

    args = parser.parse_args(sys.argv[1:])

    builder = CatalogBuilder()
    if args.type == "dataset":
        filenames = [line.strip() for line in args.files.readlines() if line]
        print(builder.dataset_catalog(filenames, args.ds_id,
                                      opendap=args.opendap,
                                      ncml_path=args.ncml))
    elif args.type == "root":
        paths = [line.strip() for line in args.catalogs.readlines() if line]
        print(builder.root_catalog(paths, args.root_dir))
