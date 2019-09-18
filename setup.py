#!/usr/bin/env python3

from setuptools import setup


ptr_params = {
    "entry_point_module": "aioexabgp/announcer/__init__",
    "test_suite": "aioexabgp.tests.base",
    "test_suite_timeout": 300,
    "required_coverage": {
        "aioexabgp/announcer/__init__.py": 40,
        "aioexabgp/announcer/fibs.py": 45,
        "aioexabgp/announcer/healthcheck.py": 60,
        "aioexabgp/exabgpparser.py": 85,
        "aioexabgp/pipes.py": 70,
        "aioexabgp/utils.py": 100,
    },
    "run_flake8": True,
    "run_black": True,
    "run_mypy": True,
}


setup(
    name="aioexabgp",
    version="2019.9.17",
    description=("asyncio exabgp base API client"),
    packages=["aioexabgp", "aioexabgp.announcer", "aioexabgp.tests"],
    url="http://github.com/cooperlees/aioexabgp/",
    author="Cooper Lees",
    author_email="me@cooperlees.com",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Development Status :: 3 - Alpha",
    ],
    python_requires=">=3.6",
    test_suite=ptr_params["test_suite"],
)
