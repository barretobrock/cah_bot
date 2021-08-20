#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from typing import List, Optional, Dict
from random import shuffle
from slacktools import BlockKitBuilder as bkb
import cah.app as cah_app
from .model import TableDecks, TableQuestionCards, TableAnswerCards


class OutOfCardsException(Exception):
    pass


class Card:
    """A Card"""
    def __init__(self, txt: str, card_id: int):
        self.txt = txt
        self.id = card_id

    def __str__(self) -> str:
        return self.txt


class QuestionCard(Card):
    """Question card"""
    card_class = 'q'

    def __init__(self, txt: str, card_id: int, req_answers: int = None):
        super().__init__(txt, card_id)
        if req_answers is not None:
            self.required_answers = req_answers
        else:
            self.required_answers = self.determine_required_answers()

    def determine_required_answers(self) -> int:
        """Determines the number of required answer cards for the question"""
        blank_matcher = re.compile(r'(_+)', re.IGNORECASE)
        match = blank_matcher.findall(self.txt)
        if match is None:
            return 1
        elif len(match) == 0:
            return 1
        else:
            return len(match)

    def modify_text(self, new_text: str):
        """Modifies the question text"""
        self.txt = new_text
        cah_app.db.session.query(TableQuestionCards).filter_by(id=self.id).update({
                'card_text': new_text})
        cah_app.db.session.commit()


class AnswerCard(Card):
    """Answer Card"""
    card_class = 'a'

    def __init__(self, txt: str, card_id: int):
        super().__init__(txt, card_id)
        # Set once dealt
        self.owner = None

    def set_owner(self, owner):
        """Takes in owner's player object and sets to the card"""
        self.owner = owner


class Pick:
    def __init__(self):
        self.owner_id = None  # type: Optional[str]
        self.pick_list = []
        self.pick_txt_list = []

    def assign(self, owner_id: str):
        """Assign id to the pick"""
        self.owner_id = owner_id

    def add_card_to_pick(self, card: Card):
        """Appends a card's text to the pick list"""
        self.pick_list.append(card)
        self.pick_txt_list.append(card.txt)

    def render_pick_list_as_str(self) -> str:
        """Renders the list of picks as a string instead of list"""
        return f'`{"` | `".join(self.pick_txt_list)}`'

    def is_empty(self) -> bool:
        """Checks if anything has been assigned to the pick yet"""
        return len(self.pick_txt_list) == 0

    def assign_and_add(self, owner: str, cards: List[Card]):
        """Assigns owner and adds cards"""
        self.assign(owner)
        for card in cards:
            self.add_card_to_pick(card)

    def clear_picks(self):
        """Clears picks (usually in preparation for a new round)"""
        self.pick_list = []
        self.pick_txt_list = []


class Hand:
    """Player's stack of cards"""
    def __init__(self, owner: str):
        self.owner = owner
        self.cards = list()
        self.pick = Pick()

    def pick_card(self, pos_list: List[int]) -> bool:
        """Picks card at index"""
        if all([-1 < x < len(self.cards) for x in pos_list]):
            if self.pick.is_empty():
                # Set our pick
                self.pick.assign_and_add(self.owner, [self.cards[x] for x in pos_list])
                # Then pop out those cards from max to min
                for p in sorted(pos_list, reverse=True):
                    card = self.cards.pop(p)
                    cah_app.db.session.query(TableAnswerCards).filter_by(id=card.id).update({
                        'times_picked': TableAnswerCards.times_picked + 1})
                    cah_app.db.session.commit()
                return True
        return False

    def mark_chosen_pick(self):
        """When a pick is chosen by the judge, this section handles marking those cards as chosen in the db
        for better tracking"""
        for card in self.pick.pick_list:
            cah_app.db.session.query(TableAnswerCards).filter_by(id=card.id).update({
                'times_chosen': TableAnswerCards.times_chosen + 1})
            cah_app.db.session.commit()

    def render_hand(self, max_selected: int = 1) -> List[Dict]:
        """Prints out the hand to the player
        Args:
            max_selected: int, the maximum allowed number of definite selections (not randpicks) to make
                if this equals 1, the multi select for definite selections will not be rendered,
                otherwise it will take the place of the individual buttons
        """
        card_blocks = []
        btn_list = []  # Button info to be made into a button group
        randbtn_list = []  # Just like above, but bear a 'rand' prefix to differentiate. These can be subset.
        for i, card in enumerate(self.cards):
            num = i + 1
            # Make a dictionary to be used as an accessory to the card's text.
            #   If we need to pick more than one card for the question, set this dictionary as None
            #   so buttons don't get confusingly rendered next to the cards.
            #   (one of these buttons == one answer, so Wizzy will deny its entry as it's under the threshold)
            card_btn_dict = bkb.make_action_button(f'{num}', f'pick-{num}', action_id=f'game-pick-{num}') if \
                max_selected == 1 else None
            card_blocks.append(bkb.make_block_section(f'*{num}*: {card.txt}', accessory=card_btn_dict))
            # We'll still build this button list, as it's used below when we need to select multiple answers
            btn_list.append({'txt': f'{num}', 'value': f'pick-{num}'})
            randbtn_list.append({'txt': f'{num}', 'value': f'randpick-{num}'})

        # This is kinda hacky, but add the divider here so that if we don't have a multiselect area to add,
        #   we still have something to add to the return statement below to make the flow a bit better
        definite_selection_area = [
            bkb.make_block_divider()
        ]
        if max_selected > 1:
            desc = f'{max_selected} picks required for this question'
            definite_selection_area += [
                bkb.make_block_multiselect(desc, f'Select {max_selected} picks', btn_list,
                                           max_selected_items=max_selected, action_id='game-multipick'),
                bkb.make_block_divider()
            ]

        rand_options = [{'txt': 'All picks', 'value': 'randpick-all'}] + randbtn_list

        return card_blocks + definite_selection_area + [
            bkb.make_block_multiselect('Randpick (all or subset)', 'Select picks', rand_options,
                                       action_id='game-randpick'),
            bkb.make_block_section('Force Close', accessory=bkb.make_action_button('Close', 'none',
                                                                                   action_id='close'))
        ]

    def take_card(self, card: AnswerCard):
        """Takes popped card and puts in hand"""
        self.cards.append(card)

    def burn_cards(self):
        """Removes all cards in the hand"""
        cah_app.db.session.query(TableAnswerCards).filter(TableAnswerCards.id.in_([x.id for x in self.cards]))\
            .update({'times_burned': TableAnswerCards.times_burned + 1})
        cah_app.db.session.commit()
        self.cards = list()

    def get_num_cards(self):
        return len(self.cards)


class Deck:
    """Deck of question and answer cards for a game"""
    def __init__(self, name: str):
        self.name = name
        self.questions_card_list = list()
        # Read in cards to deck
        # Read in questions and answers
        qcards = cah_app.db.session.query(TableQuestionCards).join(TableDecks)\
            .filter(TableDecks.name == name).all()
        acards = cah_app.db.session.query(TableAnswerCards).join(TableDecks).filter(TableDecks.name == name).all()

        self.questions_card_list = [QuestionCard(q.card_text, q.id) for q in qcards]
        self.answers_card_list = [AnswerCard(a.card_text, a.id) for a in acards]

    @property
    def num_answer_cards(self):
        return len(self.answers_card_list)

    @property
    def num_question_cards(self):
        return len(self.questions_card_list)

    def shuffle_deck(self):
        """Shuffles the deck"""
        shuffle(self.questions_card_list)
        shuffle(self.answers_card_list)

    def deal_answer_card(self) -> AnswerCard:
        """Deals an answer card in the deck."""
        card = self.answers_card_list.pop(0)
        # Increment the card usage by one
        cah_app.db.session.query(TableAnswerCards).filter_by(id=card.id).update({
            'times_drawn': TableAnswerCards.times_drawn + 1})
        cah_app.db.session.commit()
        return card

    def deal_question_card(self) -> QuestionCard:
        """Deals a question card in the deck."""
        card = self.questions_card_list.pop(0)
        # Increment the card usage by one
        cah_app.db.session.query(TableQuestionCards).filter_by(id=card.id).update({
                'times_drawn': TableQuestionCards.times_drawn + 1})
        cah_app.db.session.commit()
        return card


class Decks:
    """Possible card decks to choose"""
    def __init__(self):
        """Read in a dictionary of dfs that serve as each deck"""
        decks = cah_app.db.session.query(TableDecks).all()
        self.deck_list = [x.name for x in decks]

    def get_deck_by_name(self, name: str) -> Optional[Deck]:
        """Returns a deck matching the name provided. If no matches, returns None"""
        for d in self.deck_list:
            if d.name == name:
                return Deck(d)
        return None
