"""Configuration setup"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cah._version import get_versions
from cah.model import Base


class Common(object):
    """Configuration items common across all config types"""
    BOT_FIRST_NAME = 'Wizzy Viktorovich'
    BOT_NICKNAME = 'wizzy'
    ADMINS = ['UM35HE6R5']
    TRIGGERS = ['cah', 'c!']
    _v = get_versions()
    VERSION = _v['version']
    UPDATE_DATE = _v['date']
    DB_PATH = os.path.join(os.path.expanduser('~'), *['data', 'cahdb.db'])
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f'DB_PATH at {DB_PATH} invalid...')
    DB_URI = f'sqlite:///{DB_PATH}'
    engine = create_engine(DB_URI, isolation_level='SERIALIZABLE')
    Base.metadata.bind = engine
    SESSION = sessionmaker(bind=engine)


class Development(Common):
    """Configuration for development environment"""
    BOT_LAST_NAME = 'Debugradov'
    # MAIN_CHANNEL = 'CQ1DG4WB1'
    MAIN_CHANNEL = 'CMPV3K8AE'
    DEBUG = True


class Production(Common):
    """Configuration for development environment"""
    BOT_LAST_NAME = 'Prodborodov'
    MAIN_CHANNEL = 'CMPV3K8AE'
    DEBUG = False
