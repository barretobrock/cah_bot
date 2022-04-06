import enum
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    TIMESTAMP,
    ForeignKey
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from cah.model.base import Base


class GameStatus(enum.Enum):
    """Holds info about current status"""
    READY = enum.auto()             # App/env started
    INITIATED = enum.auto()         # Game initiated
    PLAYER_DECISION = enum.auto()   # Players still making card picks
    JUDGE_DECISION = enum.auto()    # Judge yet to choose winner
    END_ROUND = enum.auto()         # Round ended
    ENDED = enum.auto()             # Game ended


class TableGame(Base):
    """game table - stores past game info"""

    game_id = Column(Integer, primary_key=True, autoincrement=True)
    rounds = relationship('TableGameRound', back_populates='game')
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    last_update = Column(TIMESTAMP, onupdate=func.now(), server_default=func.now())
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else self.last_update - self.start_time

    def __init__(self):
        pass

    def __repr__(self) -> str:
        return f'<TableGame(id={self.game_id}, start_time={self.start_time:%F %T}, duration={self.duration})>'


class TableGameRound(Base):
    """game_round table - stores past game round info"""

    game_round_id = Column(Integer, primary_key=True, autoincrement=True)
    game_key = Column(Integer, ForeignKey('cah.game.game_id'), nullable=False)
    game = relationship('TableGame', back_populates='rounds', foreign_key=[game_key])
    question_card_key = Column(Integer, ForeignKey('cah.question_card.question_card_id'), nullable=False)
    start_time = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    last_update = Column(TIMESTAMP, onupdate=func.now(), server_default=func.now())
    end_time = Column(TIMESTAMP, nullable=True)

    @hybrid_property
    def duration(self):
        return self.end_time - self.start_time if self.end_time is not None else self.last_update - self.start_time

    def __init__(self):
        pass

    def __repr__(self) -> str:
        return f'<TableGameRound(id={self.game_round_id}, start_time={self.start_time:%F %T}, ' \
               f'duration={self.duration})>'


class TablePlayerRound(Base):
    """player-level game info"""

    player_round_id = Column(Integer, primary_key=True, autoincrement=True)
    player_key = Column(Integer, ForeignKey('cah.player.player_id'), nullable=False)
    player = relationship('TablePlayer', back_populates='rounds')
    game_key = Column(Integer, ForeignKey('cah.game.game_id'), nullable=False)
    game_round_key = Column(Integer, ForeignKey('cah.game_round.game_round_id'), nullable=False)
    score = Column(Integer, default=0, nullable=False)
    is_picked = Column(Boolean, default=False, nullable=False)
    is_judge = Column(Boolean, default=False, nullable=False)
    is_arp = Column(Boolean, default=False, nullable=False)
    is_arc = Column(Boolean, default=False, nullable=False)
    is_nuked_hand = Column(Boolean, default=False, nullable=False)
    is_nuked_hand_caught = Column(Boolean, default=False, nullable=False)

    def __init__(self):
        pass

    def __repr__(self) -> str:
        return f'<TablePlayerRound(id={self.player_round_id}, game_key={self.game_key}, ' \
               f'score={self.score})>'
