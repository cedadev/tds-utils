# tds_utils

A collection of python scripts to do various tasks to do with THREDDS data
server.

## Scripts

All scripts support `--help` for help on exact usage.

### aggregate

Read filenames of datasets from standard input and print an NcML aggregation to
standard output.

Use `--cache` to open each dataset and write the coordinate value(s) in the
NcML. This caches the values so that TDS does not need to open each file when
accessing the aggregation.

Global attributes can be added in the NcML with `--global-attr <attr>=<value>`,
and removed with `--remove-attr <name>`. These options can be given multiple
times to add/remove multiple attributes.

By default this script creates 'joinExisting' and assumes input files are
NetCDF. This behaviour can be fine tuned by [creating a custom aggregation
class](#custom-aggregation-class).

### cache_remote_aggregations

Usage: `cache_remote_aggregations <input JSON> <base THREDDS URL>`.

Send HTTP requests to OPeNDAP/WMS aggregation endpoints based on dataset IDs
found in the input JSON. This makes sure THREDDS caches aggregations before any
end-user tries to access them.

See `cache_remote_aggregations --help` for the required format of the input
JSON.

### find_ncml

Usage: `./find_ncml <catalog>`

Parse a THREDDS catalog and print paths of all referenced NcML aggregations to
stdout.

### partition_files

Read file paths from stdin and partition into sets such that paths in each set
only differ by having a different date in the directory components of the path.

Print the directory name for each group on stdout, with date characters
replaced with 'x'.

### find_netcdf

Usage: `find_netcdf <catalog>`

Parse a THREDDS catalog and list the references NetCDF files.

This script can be used with `partition_files` to check whether files in a
THREDDS catalog can likely be aggregated as one - e.g.

```bash
num=`python find_netcdf <catalog> | python partition_files | wc --lines`
if [[ $num -gt 1 ]]; then
    echo "files might be heterogeneous"
fi
```

### create_catalog

Create a THREDDS catalog from a list of NetCDF files. Can create either dataset
catalogs or root-level catalogs with links to other catalogs.

Dataset catalogs: `create_catalog dataset -f <file_list> -i <dataset_id> [--opendap] [--ncml <ncml_file>]`

Root-level catalogs: `create_catalog root -c <file_list> -r <root_dir>`

When creating a dataset catalog, `<file_list>` is a file containing a list of
NetCDF files, one per line (new lines in filenames are not supported!). For
root catalogs, `<file_list>` should contain a list of THREDDS catalogs to link
to.

## Custom aggregation classes

Creating aggregations with `aggregate` can be customised by creating a
sub-class of `tds_utils.aggregation:BaseAggregationCreator` and referencing it
with `--agg-creator-cls`.

See the source code for `BaseAggregationCreator` for the most up-to date
documentation and usage. To summarise, the following aspects of aggregation can
be changed:

* Aggregation type (e.g. `joinNew`, `joinExisting` etc...)
* Dataset reader class. This should be a subclass of `BaseDatasetReader` -- see
  the source code for the methods that must be implemented. The dataset reader
  could be overridden to, for example, read from non-NetCDF files or extract
  coordinate values in a different way (e.g. read from global attributes
  instead).
* Extra variables to add as `<variable>` elements in the NcML. This is required
  when the files being aggregated do not have a 'time' dimension (or whatever
  dimension is being aggregated along)
* Override a method to perform any additional changes to the NcML after
  aggregation is done

When creating aggregations from code with the `create_aggregation()` method
(instead of using the command-line script), one can optionally pass a list of
`AggregatedGlobalAttr` objects. These objects describe a global attribute in
the resulting NcML that should be calculated from the values in individual
files. This is useful for attributes such as `geospatial_lat_max` where the
value for the aggregation should be the maximum of the value in all constituent
files.

See the source code for `AggregatedGlobalAttr` for documentation.

## Tests

Run the tests with

```bash
pytest tds_utils/tests.py
```
