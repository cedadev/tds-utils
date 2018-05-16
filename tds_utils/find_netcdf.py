"""
Parse a THREDDS catalog and list the references NetCDF files.

Known dataset roots for specific projects are replaced with their paths on disk.
"""
import os
import sys
import argparse
import xml.etree.cElementTree as ET

from tds_utils.xml_utils import find_by_tagname


# Known project-specific dataset roots used in THREDDS catalogs
# TODO: Parse the catalog to find <datasetRoot>s as well
DATASET_ROOTS = {
    "esg_esacci": "/neodc/esacci"
}


def find_netcdf_references(catalog_filename, dataset_roots={}):
    for el in find_by_tagname(catalog_filename, "dataset"):
        if "urlPath" in el.attrib:
            path = el.get("urlPath")

            # Replace dataset roots if any match
            for root, location in dataset_roots.items():
                if path.startswith(root):
                    path = path.replace(root, location)
                    break
            yield path


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "catalog",
        help="THREDDS catalog to parse"
    )
    args = parser.parse_args(sys.argv[1:])
    filenames = find_netcdf_references(args.catalog, dataset_roots=DATASET_ROOTS)
    for filename in filenames:
        print(filename)
