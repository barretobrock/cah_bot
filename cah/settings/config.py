"""Configuration setup"""
import pathlib
from typing import Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cah import (
    __update_date__,
    __version__,
)
from cah.model.base import Base

HOME = pathlib.Path().home()
KEY_DIR = HOME.joinpath('keys')
LOG_DIR = HOME.joinpath('logs')


def read_secrets(path_obj: pathlib.Path) -> Dict:
    secrets = {}
    with path_obj.open('r') as f:
        for item in f.readlines():
            if item.startswith('#'):
                continue
            k, v = item.split('=', 1)
            secrets[k] = v.strip()
    return secrets


class Common(object):
    """Configuration items common across all config types"""
    ENV = 'DEV'
    BOT_FIRST_NAME = 'Wizzy Boborkadork Viktorovich'
    BOT_NICKNAME = 'wizzy'
    ADMINS = ['UM35HE6R5']
    TRIGGERS = ['cah', 'c!']
    LOG_DIR = HOME.joinpath('logs')

    VERSION = __version__
    UPDATE_DATE = __update_date__

    LOG_LEVEL = 'DEBUG'
    PORT = 5004

    SECRETS = None
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://{usr}:{pwd}@{host}:{port}/{database}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION = None

    @classmethod
    def load_secrets(cls):
        secrets_path = KEY_DIR.joinpath('cah-secretprops.properties')
        cls.SECRETS = read_secrets(secrets_path)

    @classmethod
    def build_db_engine(cls):
        """Builds database engine, sets SESSION"""
        if cls.SECRETS is None:
            cls.load_secrets()
        cls.SQLALCHEMY_DATABASE_URI = cls.SQLALCHEMY_DATABASE_URI.format(**cls.SECRETS)
        engine = create_engine(cls.SQLALCHEMY_DATABASE_URI, isolation_level='SERIALIZABLE')
        Base.metadata.bind = engine
        cls.SESSION = sessionmaker(bind=engine)


class Development(Common):
    """Configuration for development environment"""
    ENV = 'DEV'
    BOT_LAST_NAME = 'Debugradov'
    MAIN_CHANNEL = 'CQ1DG4WB1'
    TRIGGERS = ['wah', 'w!']
    DEBUG = True
    USE_RELOADER = False


class Production(Common):
    """Configuration for development environment"""
    ENV = 'PROD'
    BOT_LAST_NAME = 'Prodborodov'
    MAIN_CHANNEL = 'C05HPAMHG4Q'
    TRIGGERS = ['cah', 'c!']
    DEBUG = False
