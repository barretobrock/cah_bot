from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from .model import Base
from .settings import auto_config


def get_session() -> Session:
    """Retrieves a session for communicating with the database"""
    # Load database
    engine = create_engine(f'sqlite:///{auto_config.DB_PATH}')
    Base.metadata.bind = engine
    db_session = sessionmaker(bind=engine)
    return db_session()
