from sqlalchemy import Column, VARCHAR, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from .base import Base


class TablePlayers(Base):
    """players table"""
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True, autoincrement=True)
    slack_id = Column(VARCHAR(50), nullable=False, unique=True)
    name = Column(VARCHAR(80), nullable=False)
    honorific = Column(VARCHAR(255))
    is_dm_cards = Column(Boolean, default=True, nullable=False)
    is_auto_randpick = Column(Boolean, default=False, nullable=False)
    is_auto_randchoose = Column(Boolean, default=False, nullable=False)
    is_skip = Column(Boolean, default=False, nullable=False)
    current_game = relationship("TableGames", back_populates='players')
    total_score = Column(Integer, default=0, nullable=False)
    all_rounds = relationship("TablePlayerRounds", back_populates='player')
    total_decknukes_issued = Column(Integer, default=0, nullable=False)
    total_games_played = Column(Integer, default=0, nullable=False)

    @hybrid_property
    def current_score(self):
        return sum()
