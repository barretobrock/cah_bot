from sqlalchemy import Column, VARCHAR, Integer, Boolean, TIMESTAMP, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from .base import Base


class TableBotSettings(Base):
    """games table - stores past game info"""
    __tablename__ = 'botsettings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    last_update = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
