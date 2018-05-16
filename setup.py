from setuptools import setup, find_packages

with open("requirements.txt") as req_file:
    requirements = [line.strip() for line in req_file]

setup(
    name="tds_utils",
    version="0.0.1",
    description="Scripts to perform various tasks to do with THREDDS data server",
    packages=find_packages(),
    install_requires=requirements,
    extras_require={
        "test": ["pytest"]
    },
    entry_points={
        "console_scripts": [
            "aggregate=tds_utils.aggregate:main",
            "cache_remote_aggregations=tds_utils.cache_remote_aggregations:main",
            "find_ncml=tds_utils.find_ncml:main",
            "find_netcdf=tds_utils.find_netcdf:main",
            "partition_files=tds_utils.partition_files:main"
        ]
    }
)
