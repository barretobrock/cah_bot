from sqlalchemy import Column, VARCHAR, Integer, Boolean, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from .base import Base


class Games(Base):
    """games table - stores past game info"""
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rounds = Column(Integer, default=0, nullable=False)
    players = Column(Integer, default=0, nullable=False)
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    last_update = Column(TIMESTAMP, onupdate=func.now())
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else self.last_update - self.start_time
