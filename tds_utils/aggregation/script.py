"""
Read filenames of datasets from standard input and print an NcML aggregation to
standard output.
"""
import os
import sys
import argparse
from importlib import import_module

from tds_utils.aggregation import AggregationCreator
from tds_utils.xml_utils import element_to_string


def python_class(string):
    """
    Import and return a class from a string of the form 'module.path:class'
    """
    try:
        module_name, cls_name = string.split(":")
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Class should be specifed as module.path:class_name"
        )
    module = import_module(module_name)
    return getattr(module, cls_name)


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
        help="Open files to read coordinate values to include in the NcML. "
             "This caches the values so that TDS does not need to open each "
             "file when accessing the aggregation [default: %(default)s]"
    )
    parser.add_argument(
        "--agg-creator-cls",
        default=AggregationCreator,
        type=python_class,
        help="Python class to use to create the aggregation. This should be a "
             "sub-class of `tds_utils.aggregation:BaseAggregationCreator'. "
             "See the source code for usage"
    )
    parser.add_argument(
        "-g", "--global-attr",
        default=[],
        action="append",
        help="Global attribute to set in the generated aggregation. This "
             "should be of the form '<attr>=<value>'. Can be given multiple "
             "times"
    )

    args = parser.parse_args(sys.argv[1:])
    path_list = [line for line in sys.stdin.read().split(os.linesep) if line]
    creator = args.agg_creator_cls(args.dimension)

    # Build global attributes dict
    global_attrs = {}
    for attr_string in args.global_attr:
        split = map(str.strip, attr_string.split("="))
        try:
            attr, value = split
        except ValueError:
            parser.error("Invalid global attribute '{}'. Should be of the "
                         "form '<attr>=<value>'".format(attr_string))
        global_attrs[attr] = value

    ncml_el = creator.create_aggregation(path_list, cache=args.cache,
                                         global_attrs=global_attrs)
    print(element_to_string(ncml_el))
