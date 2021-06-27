from sqlalchemy import Column, VARCHAR, Integer, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from .base import Base


class TableGames(Base):
    """games table - stores past game info"""
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(VARCHAR(50), nullable=False)
    rounds = Column(Integer, default=0, nullable=False)
    players = Column(Integer, default=0, nullable=False)
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    last_update = Column(TIMESTAMP, onupdate=func.now())
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else self.last_update - self.start_time


class TableGameRounds(Base):
    """gamerounds table - stores past gameround info"""
    __tablename__ = 'gamerounds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else None
