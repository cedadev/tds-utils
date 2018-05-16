# tds_utils

A collection of python scripts to do various tasks to do with THREDDS data
server.

## Scripts

All scripts support `--help` for help on exact usage.

### aggregate.py

Read filenames of NetCDF datasets from standard input and print an NcML
aggregation to standard output.

Use `--cache` to open each dataset and write the coordinate value(s) in the
NcML. This caches the values so that TDS does not need to open each file when
accessing the aggregation.

### cache_remote_aggregations.py

Usage: `cache_remote_aggregations.py <input JSON> <base THREDDS URL>`.

Send HTTP requests to OPeNDAP/WMS aggregation endpoints based on dataset IDs
found in the input JSON. This makes sure THREDDS caches aggregations before any
end-user tries to access them.

See `cache_remote_aggregations --help` for the required format of the input
JSON.

### find_ncml.py

Usage: `./find_ncml.py <catalog>`

Parse a THREDDS catalog and print paths of all referenced NcML aggregations to
stdout.

### partition_files.py

Read file paths from stdin and partition into sets such that paths in each set
only differ by having a different date in the directory components of the path.

Print the directory name for each group on stdout, with date characters
replaced with 'x'.

### find_netcdf.py

Usage: `find_netcdf.py <catalog>`

Parse a THREDDS catalog and list the references NetCDF files.

This script can be used with `partition_files.py` to check whether files in a
THREDDS catalog can likely be aggregated as one - e.g.

```bash
num=`python find_netcdf.py <catalog> | python partition_files.py | wc --lines`
if [[ $num -gt 1 ]]; then
    echo "files might be heterogeneous"
fi
```

## Tests

Run the tests with

```bash
pytest tds_utils/tests.py
```
