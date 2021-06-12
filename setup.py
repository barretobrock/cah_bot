#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup CAH bot.
"""
import os
import versioneer
from setuptools import setup, find_packages
from config import config_dict


here_dir = os.path.abspath(os.path.dirname(__file__))
# Package Requirements
fpath = os.path.join(here_dir, 'requirements.txt')
with open(fpath, 'r') as f:
    reqs_raw = f.read()
reqs_list = reqs_raw.strip().split('\n')

setup_args = {
    'version': versioneer.get_version(),
    'cmdclass': versioneer.get_cmdclass(),
    'packages': find_packages(exclude=['tests']),
    'install_requires': reqs_list,
}
setup_args.update(config_dict)

setup(**setup_args)
