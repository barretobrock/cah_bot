#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup CAH bot.
"""
import os
import versioneer
from setuptools import setup, find_packages


here_dir = os.path.abspath(os.path.dirname(__file__))
init_fp = os.path.join(here_dir, *['cah_bot', '__init__.py'])

setup_args = {
    'name': 'cah_bot',
    'version': versioneer.get_version(),
    'cmdclass': versioneer.get_cmdclass(),
    'license': 'MIT',
    'description': 'A library for playing Cards Against Humanity on Slack',
    'url': 'https://github.com/barretobrock/cah_bot',
    'author': 'Barret Obrock',
    'author_email': 'barret@barretobrock.ee',
    'packages': find_packages(exclude=['tests']),
    'dependency_links': [
        'https://github.com/barretobrock/slacktools/tarball/master#egg=slacktools'
    ],
    'install_requires': [
        'slacktools',
        'flask==1.1.1',
        'slackeventsapi==2.1.0',
        'requests>=2.20.0'
    ]
}

setup(**setup_args)
