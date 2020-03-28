#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import pandas as pd
from random import shuffle
from slacktools import BlockKitBuilder


class Card:
    """A Card"""
    def __init__(self, txt):
        self.txt = txt

    def __str__(self):
        return self.txt


class QuestionCard(Card):
    """Question card"""
    card_class = 'q'

    def __init__(self, txt, req_answers=None):
        super().__init__(txt)
        if req_answers is not None:
            self.required_answers = req_answers
        else:
            self.required_answers = self.determine_required_answers()

    def determine_required_answers(self):
        """Determines the number of required answer cards for the question"""
        blank_matcher = re.compile(r'(_+)', re.IGNORECASE)
        match = blank_matcher.findall(self.txt)
        if match is None:
            return 1
        elif len(match) == 0:
            return 1
        else:
            return len(match)


class AnswerCard(Card):
    """Answer Card"""
    card_class = 'a'

    def __init__(self, txt):
        super().__init__(txt)
        # Set once dealt
        self.owner = None

    def set_owner(self, owner):
        """Takes in owner's player object and sets to the card"""
        self.owner = owner


class Hand:
    """Player's stack of cards"""
    def __init__(self):
        self.cards = list()
        self.picks = None
        self.bkb = BlockKitBuilder()

    def pick_card(self, pos_list):
        """Picks card at index"""
        if all([-1 < x < len(self.cards) for x in pos_list]):
            if self.picks is None:
                # Set our picks
                self.picks = [self.cards[x] for x in pos_list]
                # Then pop out those cards from max to min
                for p in sorted(pos_list, reverse=True):
                    _ = self.cards.pop(p)
                return True
        return False

    def render_hand(self, max_selected=1):
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
            card_btn_dict = self.bkb.make_block_button(f'{num}', f'pick-{num}') if max_selected == 1 else None
            card_blocks.append(self.bkb.make_block_section(f'*{num}*: {card.txt}', accessory=card_btn_dict))
            # We'll still build this button list, as it's used below when we need to select multiple answers
            btn_list.append({'txt': f'{num}', 'value': f'pick-{num}'})
            randbtn_list.append({'txt': f'{num}', 'value': f'randpick-{num}'})

        # This is kinda hacky, but add the divider here so that if we don't have a multiselect area to add,
        #   we still have something to add to the return statement below to make the flow a bit better
        definite_selection_area = [
            self.bkb.make_block_divider()
        ]
        if max_selected > 1:
            desc = f'{max_selected} picks required for this question'
            definite_selection_area += [
                self.bkb.make_block_multiselect(desc, f'Select {max_selected} picks', btn_list,
                                                max_selected_items=max_selected),
                self.bkb.make_block_divider()
            ]

        rand_options = [{'txt': 'All picks', 'value': 'randpick-all'}] + randbtn_list

        return card_blocks + definite_selection_area + [
            self.bkb.make_block_multiselect('Randpick (all or subset)', 'Select picks', rand_options)
        ]

    def take_card(self, card):
        """Takes popped card and puts in hand"""
        self.cards.append(card)

    def burn_cards(self):
        """Removes all cards in the hand"""
        self.cards = list()


class CardPot:
    """Stores played cards during round"""
    def __init__(self):
        self.cards = list()

    def receive_card(self, card):
        """Takes in a played card"""
        self.cards.append(card)

    def clear_pot(self):
        """Remove all played cards once judge has made a decison"""
        self.cards = list()


class Deck:
    """Deck of question and answer cards for a game"""
    def __init__(self, name, df):
        self.name = name
        self.questions_card_list = list()
        # Read in cards to deck
        # First read in questions
        # This is used to ensure no duplicate questions
        question_list = []
        for i, row in df.iterrows():
            question = row['questions']
            if question in question_list:
                continue
            if question != '' or not pd.isnull(question):
                if 'req' in row.index.values:
                    # Get count of required questions
                    no_req_qs = row['req']
                    if isinstance(no_req_qs, int):
                        self.questions_card_list.append(QuestionCard(question, req_answers=int(no_req_qs)))
                        question_list.append(question)
                else:
                    # No required number of answers. Try to estimate it
                    self.questions_card_list.append(QuestionCard(question))
                    question_list.append(question)

        # Read in answers
        a_card_list = df.loc[(~df['answers'].isnull()) & (df['answers'] != ''), 'answers'].unique().tolist()
        self.answers_card_list = [AnswerCard(x) for x in a_card_list]

    def shuffle_deck(self):
        """Shuffles the deck"""
        shuffle(self.questions_card_list)
        shuffle(self.answers_card_list)

    def deal_answer_card(self):
        """Deals an answer card in the deck."""
        return self.answers_card_list.pop(0)

    def deal_question_card(self):
        """Deals a question card in the deck."""
        return self.questions_card_list.pop(0)


class Decks:
    """Possible card decks to choose"""
    def __init__(self, dict_of_dfs):
        """Read in a dictionary of dfs that serve as each deck"""
        self.deck_list = []
        for k, v in dict_of_dfs.items():
            self.deck_list.append(Deck(k, v))
        self.deck_names = [x.name for x in self.deck_list]

    def get_deck_by_name(self, name):
        """Returns a deck matching the name provided. If no matches, returns None"""
        for d in self.deck_list:
            if d.name == name:
                return d
        return None

