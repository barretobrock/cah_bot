#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from random import shuffle


class Card:
    """A Card"""
    def __init__(self, txt):
        self.txt = txt

    def __str__(self):
        return self.txt


class QuestionCard(Card):
    """Question card"""
    card_class = 'q'

    def __init__(self, txt):
        super().__init__(txt)
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
        self.pick = None

    def pick_card(self, pos):
        """Picks card at index"""
        if -1 < pos < len(self.cards):
            if self.pick is None:
                self.pick = self.cards.pop(pos)
                return True
        return False

    def render_hand(self):
        """Prints out the hand to the player"""
        return '\t{}'.format('\n'.join(['\t`{}`: {}'.format(i + 1, x) for i, x in enumerate(self.cards)]))

    def take_card(self, card):
        """Takes popped card and puts in hand"""
        self.cards.append(card)


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
        self.questions_card_list = None
        self.answers_card_list = None
        # Read in cards to deck
        for part in ['questions', 'answers']:
            card_list = df.loc[(~df[part].isnull()) & (df[part] != ''), part].unique().tolist()
            if part == 'questions':
                rendered_list = [QuestionCard(x) for x in card_list]
            else:
                rendered_list = [AnswerCard(x) for x in card_list]
            self.__setattr__('{}_card_list'.format(part), rendered_list)

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

