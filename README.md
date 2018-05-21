# tds_utils

A collection of python scripts to do various tasks to do with THREDDS data
server.

## Scripts

All scripts support `--help` for help on exact usage.

### aggregate

Read filenames of NetCDF datasets from standard input and print an NcML
aggregation to standard output.

Use `--cache` to open each dataset and write the coordinate value(s) in the
NcML. This caches the values so that TDS does not need to open each file when
accessing the aggregation.

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

## Tests

Run the tests with

```bash
pytest tds_utils/tests.py
```
