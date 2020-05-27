from setuptools import setup, find_packages

setup(
    name="tds-utils",
    version="0.0.1",
    description="Scripts to perform various tasks to do with THREDDS data server",
    packages=find_packages(),
    install_requires=[
        'requests',
        'netCDF4',
        'numpy',
        'Jinja2',
        'tqdm'
    ],
    extras_require={
        "test": ["pytest"]
    },
    package_data={
        "tds_utils": ["templates/*.xml"]
    },
    entry_points={
        "console_scripts": [
            "aggregate=tds_utils.aggregation.script:main",
            "cache_remote_aggregations=tds_utils.cache_remote_aggregations:main",
            "create_catalog=tds_utils.create_catalog:main",
            "find_ncml=tds_utils.find_ncml:main",
            "find_netcdf=tds_utils.find_netcdf:main",
            "partition_files=tds_utils.partition_files:main"
        ]
    }
)
