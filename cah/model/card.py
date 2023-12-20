from sqlalchemy import (
    VARCHAR,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship

# local imports
from cah.model.base import Base


class TableAnswerCard(Base):
    """answer card table"""
    answer_card_id = Column(Integer, primary_key=True, autoincrement=True)
    deck_key = Column(Integer, ForeignKey('cah.deck.deck_id'), nullable=False)
    deck = relationship('TableDeck', backref='answer_cards')
    card_text = Column(Text, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)
    times_picked = Column(Integer, default=0, nullable=False)
    times_burned = Column(Integer, default=0, nullable=False)
    times_chosen = Column(Integer, default=0, nullable=False)

    def __init__(self, card_text: str, deck_key: int):
        self.card_text = card_text
        self.deck_key = deck_key

    def __repr__(self) -> str:
        return f'<TableAnswerCard(id={self.answer_card_id}, deck_key={self.deck_key} text={self.card_text[:20]})>'


class TableQuestionCard(Base):
    """question card table"""

    question_card_id = Column(Integer, primary_key=True, autoincrement=True)
    deck_key = Column(Integer, ForeignKey('cah.deck.deck_id'), nullable=False)
    deck = relationship('TableDeck', backref='question_cards')
    card_text = Column(Text, nullable=False)
    responses_required = Column(Integer, default=1, nullable=False)
    times_drawn = Column(Integer, default=0, nullable=False)

    def __init__(self, card_text: str, deck_key: int, responses_required: int):
        self.card_text = card_text
        self.deck_key = deck_key
        self.responses_required = responses_required

    def __repr__(self) -> str:
        return f'<TableQuestionCard(id={self.question_card_id}, deck_key={self.deck_key} ' \
               f'text={self.card_text[:20]})>'


class TablePlayerHand(Base):
    """player's hand table - This represents the player's current hand"""

    hand_id = Column(Integer, primary_key=True, autoincrement=True)
    card_pos = Column(Integer, nullable=False)
    player_key = Column(Integer, ForeignKey('cah.player.player_id'), nullable=False)
    answer_card_key = Column(Integer, ForeignKey('cah.answer_card.answer_card_id'), nullable=False)
    is_picked = Column(Boolean, default=False, nullable=False)
    is_nuked = Column(Boolean, default=False, nullable=False)

    def __init__(self, card_pos: int, player_key: int, answer_card_key: int):
        self.card_pos = card_pos
        self.player_key = player_key
        self.answer_card_key = answer_card_key

    def __repr__(self) -> str:
        return f'<TableHand(id={self.hand_id}, pos={self.card_pos} pid={self.player_key})>'


class TablePlayerPick(Base):
    """log of past players' picks - This represents a log of cards played

    Attributes:
        card_order: the order in which the card goes (when picking multiple)
    """

    pick_id = Column(Integer, primary_key=True, autoincrement=True)
    game_round_key = Column(Integer, ForeignKey('cah.game_round.game_round_id'), nullable=False)
    player_key = Column(Integer, ForeignKey('cah.player.player_id'), nullable=False)
    slack_user_hash = Column(VARCHAR(50), nullable=False)
    card_order = Column(Integer, nullable=False)
    answer_card_key = Column(Integer, ForeignKey('cah.answer_card.answer_card_id'), nullable=False)

    def __init__(self, player_key: int, game_round_key: int, slack_user_hash: str, card_order: int, answer_card_key: int):
        self.player_key = player_key
        self.game_round_key = game_round_key
        self.slack_user_hash = slack_user_hash
        self.card_order = card_order
        self.answer_card_key = answer_card_key

    def __repr__(self) -> str:
        return f'<TablePlayerPick(id={self.pick_id}, order={self.card_order} pid={self.player_key})>'
