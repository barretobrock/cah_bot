from typing import Tuple
from sqlalchemy import (
    Column,
    VARCHAR,
    Integer,
    Boolean,
    event,
    select
)
from sqlalchemy.sql import (
    func,
    and_
)
from sqlalchemy.orm import (
    relationship,
    column_property,
    mapper
)
from sqlalchemy.dialects.postgresql import INT4RANGE
from psycopg2.extras import NumericRange
# local imports
from cah.model.base import Base
from cah.model.game import TablePlayerRound


class TablePlayer(Base):
    """player table"""

    player_id = Column(Integer, primary_key=True, autoincrement=True)
    slack_user_hash = Column(VARCHAR(50), nullable=False, unique=True)
    display_name = Column(VARCHAR(120), nullable=False)
    honorific = Column(VARCHAR(255), default='')
    is_dm_cards = Column(Boolean, default=True, nullable=False)
    is_auto_randpick = Column(Boolean, default=False, nullable=False)
    is_auto_randchoose = Column(Boolean, default=False, nullable=False)
    is_skip = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rounds = relationship('TablePlayerRound', back_populates='player')

    def __init__(self, slack_user_hash: str, display_name: str, honorific: str, is_dm_cards: bool = True,
                 is_auto_randpick: bool = False, is_auto_randchoose: bool = False, is_skip: bool = False):
        self.slack_user_hash = slack_user_hash,
        self.display_name = display_name
        self.honorific = honorific
        self.is_dm_cards = is_dm_cards
        self.is_auto_randpick = is_auto_randpick
        self.is_auto_randchoose = is_auto_randchoose
        self.is_skip = is_skip

    def __repr__(self) -> str:
        return f'<TablePlayer(id={self.player_id}, slack_hash={self.slack_user_hash}, ' \
               f'display_name={self.display_name}, honorific={self.honorific})>'


class TableHonorific(Base):
    """honorific table"""

    honorific_id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(VARCHAR(200), nullable=False)
    score_range = Column(INT4RANGE, nullable=False)

    def __init__(self, text: str, score_range: Tuple[int, int]):
        self.text = text
        self.score_range = NumericRange(*score_range)

    def __repr__(self) -> str:
        return f'<TableHonorific(id={self.honorific_id}, score_range={self.score_range}, text={self.text})>'


@event.listens_for(mapper, 'mapper_configured')
def set_thread_count(mapper_, cls) -> None:
    if issubclass(cls, TablePlayer):
        # Calculate total score
        total_score_subquery = (
            select([func.coalesce(func.sum(TablePlayerRound.score), 0)])
            .where(TablePlayerRound.player_key == cls.player_id)
            .label('total_score')
        )
        cls.total_score = column_property(total_score_subquery, deferred=True)

        # Calculate games played
        total_games_subquery = (
            select([func.distinct(TablePlayerRound.game_key)])
            .where(TablePlayerRound.player_key == cls.player_id)
            .label('total_games_played')
        )
        cls.total_games_played = column_property(total_games_subquery, deferred=True)

        # Calculate decknukes issued
        total_decknukes_issued_subquery = (
            select([func.count(TablePlayerRound.is_nuked_hand)])
            .where(and_(
                TablePlayerRound.player_key == cls.player_id,
                TablePlayerRound.is_nuked_hand
            ))
            .label('total_decknukes_issued')
        )
        cls.total_decknukes_issued = column_property(total_decknukes_issued_subquery, deferred=True)

        # Calculate decknukes caught
        total_decknukes_caught_subquery = (
            select([func.count(TablePlayerRound.is_nuked_hand_caught)])
            .where(and_(
                TablePlayerRound.player_key == cls.player_id,
                TablePlayerRound.is_nuked_hand_caught
            ))
            .label('total_decknukes_caught')
        )
        cls.total_decknukes_caught = column_property(total_decknukes_caught_subquery, deferred=True)
