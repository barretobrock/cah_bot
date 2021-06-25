#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from ._version import get_versions
__version__ = get_versions()['version']
__update_date__ = get_versions()['date']
del get_versions
