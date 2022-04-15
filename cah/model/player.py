from typing import Tuple
from sqlalchemy import (
    Column,
    VARCHAR,
    Integer,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
# local imports
from cah.model.base import Base


class TablePlayer(Base):
    """player table"""

    player_id = Column(Integer, primary_key=True, autoincrement=True)
    slack_user_hash = Column(VARCHAR(50), nullable=False, unique=True)
    display_name = Column(VARCHAR(120), nullable=False)
    honorific = Column(VARCHAR(255), default='')
    is_dm_cards = Column(Boolean, default=True, nullable=False)
    is_auto_randpick = Column(Boolean, default=False, nullable=False)
    is_auto_randchoose = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rounds = relationship('TablePlayerRound', back_populates='player')
    avi_url = Column(VARCHAR(255), nullable=False)

    def __init__(self, slack_user_hash: str, display_name: str, avi_url: str, honorific: str = '',
                 is_dm_cards: bool = True, is_auto_randpick: bool = False, is_auto_randchoose: bool = False,
                 is_active: bool = True):
        self.slack_user_hash = slack_user_hash,
        self.display_name = display_name
        self.avi_url = avi_url
        self.honorific = honorific
        self.is_dm_cards = is_dm_cards
        self.is_auto_randpick = is_auto_randpick
        self.is_auto_randchoose = is_auto_randchoose
        self.is_active = is_active

    @hybrid_property
    def full_name(self):
        return f'{self.display_name} {self.honorific.title()}'

    def __repr__(self) -> str:
        return f'<TablePlayer(id={self.player_id}, slack_hash={self.slack_user_hash}, ' \
               f'display_name={self.display_name}, honorific={self.honorific})>'


class TableHonorific(Base):
    """honorific table"""

    honorific_id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(VARCHAR(200), nullable=False)
    score_lower_lim = Column(Integer, nullable=False)
    score_upper_lim = Column(Integer, nullable=False)

    def __init__(self, text: str, score_range: Tuple[int, int]):
        self.text = text
        self.score_lower_lim, self.score_upper_lim = score_range

    def __repr__(self) -> str:
        return f'<TableHonorific(id={self.honorific_id}, ' \
               f'score_range=({self.score_lower_lim},{self.score_upper_lim}), text={self.text})>'
