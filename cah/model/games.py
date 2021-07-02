import enum
from sqlalchemy import Column, VARCHAR, Integer, Boolean, TIMESTAMP, ForeignKey, CheckConstraint, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from .base import Base


class GameStatuses(enum.Enum):
    """Holds info about current status"""
    ready = 'ready'                         # App/env started
    initiated = 'initiated'                 # Game initiated
    players_decision = 'players_decision'   # Players still making card picks
    judge_decision = 'judge_decision'       # Judge yet to choose winner
    end_round = 'end_round'                 # Round ended
    ended = 'ended'                         # Game ended


class TableGames(Base):
    """games table - stores past game info"""
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Enum(GameStatuses), default=GameStatuses.initiated, nullable=False)
    rounds = relationship('TableGameRounds', back_populates='game')
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
    game = relationship("TableGames", back_populates='rounds')
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else None


class TablePlayerRounds(Base):
    """player-level game info"""

    __tablename__ = 'playerrounds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('players.id'))
    player = relationship("TablePlayers", back_populates='all_rounds')
    game_id = Column(Integer, ForeignKey('games.id'))
    round_id = Column(Integer, ForeignKey('gamerounds.id'))
    score = Column(Integer, default=0, nullable=False)
    is_picked = Column(Boolean, default=False, nullable=False)
    is_judge = Column(Boolean, default=False, nullable=False)
    is_nuked_hand = Column(Boolean, default=False, nullable=False)
    is_nuked_hand_caught = Column(Boolean, default=False, nullable=False)


class TableGameSettings(Base):
    """gamesettings table - """

    __tablename__ = 'gamesettings'
    __table_args__ = (
        CheckConstraint('id < 2', name='settings_row_limit1'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    is_ping_winner = Column(Boolean, default=True, nullable=False)
    is_ping_judge = Column(Boolean, default=True, nullable=False)
    decknuke_penalty = Column(Integer, default=-3, nullable=False)
    judge_order_divider = Column(VARCHAR, default=':finger-wag-right:', nullable=False)
    last_update = Column(TIMESTAMP, onupdate=func.now())
