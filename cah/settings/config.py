"""Configuration setup"""
from cah import (
    __version__,
    __update_date__
)


class Common(object):
    """Configuration items common across all config types"""
    BOT_FIRST_NAME = 'Wizzy Boborkadork Viktorovich'
    BOT_NICKNAME = 'wizzy'
    ADMINS = ['UM35HE6R5']
    TRIGGERS = ['cah', 'c!']

    VERSION = __version__
    UPDATE_DATE = __update_date__


class Development(Common):
    """Configuration for development environment"""
    ENV = 'DEV'
    BOT_LAST_NAME = 'Debugradov'
    MAIN_CHANNEL = 'CQ1DG4WB1'
    TRIGGERS = ['wah', 'w!']
    DEBUG = True


class Production(Common):
    """Configuration for development environment"""
    ENV = 'PROD'
    BOT_LAST_NAME = 'Prodborodov'
    MAIN_CHANNEL = 'CMPV3K8AE'
    TRIGGERS = ['cah', 'c!']
    DEBUG = False
