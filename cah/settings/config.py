"""Configuration setup"""
from cah._version import get_versions


class Common(object):
    """Configuration items common across all config types"""
    BOT_FIRST_NAME = 'Wizzy Viktorovich'
    BOT_NICKNAME = 'wizzy'
    ADMINS = ['UM35HE6R5']
    TRIGGERS = ['cah', 'c!']
    v = get_versions()
    VERSION = v['version']
    UPDATE_DATE = v['date']


class Development(Common):
    """Configuration for development environment"""
    BOT_LAST_NAME = 'Debugradov'
    MAIN_CHANNEL = 'CQ1DG4WB1'
    DEBUG = True


class Production(Common):
    """Configuration for development environment"""
    BOT_LAST_NAME = 'Prodborodov'
    MAIN_CHANNEL = 'CMPV3K8AE'
    DEBUG = False
