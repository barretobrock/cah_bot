#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup CAH bot.
"""
import os
import yaml
import versioneer
from setuptools import setup, find_packages


# Read in package info via YAML
with open('config.yaml') as f:
    package_info = yaml.load(f, Loader=yaml.FullLoader)

PACKAGE = package_info['REPO']['NAME']
DESC = package_info['REPO']['DESC']
URL = package_info['REPO']['URL']
DEPS = package_info['REPO']['DEPS']
here_dir = os.path.abspath(os.path.dirname(__file__))
init_fp = os.path.join(here_dir, *[PACKAGE, '__init__.py'])

# Package Requirements
fpath = os.path.join(here_dir, 'requirements.txt')
with open(fpath, 'r') as f:
    reqs_raw = f.read()
reqs_list = reqs_raw.strip().split('\n')

setup_args = {
    'name': PACKAGE,
    'version': versioneer.get_version(),
    'cmdclass': versioneer.get_cmdclass(),
    'license': 'GPL',
    'description': DESC,
    'url': URL,
    'author': 'Barret Obrock',
    'packages': find_packages(exclude=['tests']),
    'dependency_links': DEPS,
    'install_requires': reqs_list
}

setup(**setup_args)
