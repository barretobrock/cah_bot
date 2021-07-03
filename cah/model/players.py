from sqlalchemy import Column, VARCHAR, Integer, Boolean, event, select
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, column_property, mapper
# local imports
from .base import Base
from .games import TablePlayerRounds


class TablePlayers(Base):
    """players table"""
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True, autoincrement=True)
    slack_id = Column(VARCHAR(50), nullable=False, unique=True)
    name = Column(VARCHAR(80), nullable=False)
    honorific = Column(VARCHAR(255), default='')
    is_dm_cards = Column(Boolean, default=True, nullable=False)
    is_auto_randpick = Column(Boolean, default=False, nullable=False)
    is_auto_randchoose = Column(Boolean, default=False, nullable=False)
    is_skip = Column(Boolean, default=False, nullable=False)
    rounds = relationship('TablePlayerRounds', back_populates='player')


@event.listens_for(mapper, 'mapper_configured')
def set_thread_count(mapper, cls) -> None:
    if issubclass(cls, TablePlayers):
        # Calculate total score
        total_score_subquery = (
            select([func.sum(TablePlayerRounds.score)])
            .where(TablePlayerRounds.player_id == cls.id)
            .label('total_score')
        )
        cls.total_score = column_property(total_score_subquery, deferred=True)

        # Calculate games played
        total_games_subquery = (
            select([func.distinct(TablePlayerRounds.game_id)])
            .where(TablePlayerRounds.player_id == cls.id)
            .label('total_games_played')
        )
        cls.total_games_played = column_property(total_games_subquery, deferred=True)

        # Calculate decknukes issued
        total_decknukes_issued_subquery = (
            select([func.count(TablePlayerRounds.is_nuked_hand)])
            .where(TablePlayerRounds.player_id == cls.id)
            .label('total_decknukes_issued')
        )
        cls.total_decknukes_issued = column_property(total_decknukes_issued_subquery, deferred=True)

        # Calculate decknukes caught
        total_decknukes_caught_subquery = (
            select([func.count(TablePlayerRounds.is_nuked_hand_caught)])
            .where(TablePlayerRounds.player_id == cls.id)
            .label('total_decknukes_caught')
        )
        cls.total_decknukes_caught = column_property(total_decknukes_caught_subquery, deferred=True)
