from sqlalchemy import Column, VARCHAR, Integer, ForeignKey
# local imports
from .base import Base


class TablePlayers(Base):
    """players table"""
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True, autoincrement=True)
    slack_id = Column(VARCHAR(50), nullable=False, unique=True)
    name = Column(VARCHAR(80), nullable=False)
    current_score = Column(Integer, default=0, nullable=False)
    total_score = Column(Integer, default=0, nullable=False)
    total_rounds_played = Column(Integer, default=0, nullable=False)
    total_decknukes_issued = Column(Integer, default=0, nullable=False)
    total_games_played = Column(Integer, default=0, nullable=False)


class TablePlayerGames(Base):
    """player-level game info"""

    __tablename__ = 'playergames'

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey('players.id'))
    game_id = Column(Integer, ForeignKey('games.id'))
    score = Column(Integer, default=0, nullable=False)
    decknukes_issued = Column(Integer, default=0, nullable=False)
    decknukes_caught = Column(Integer, default=0, nullable=False)
    rounds_played = Column(Integer, default=0, nullable=False)
