#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime
from random import shuffle
from slacktools import BlockKitBuilder
from .players import Players


class GameStatus:
    """Holds info about current status"""
    game_order = [
        'stahted',
        'initiated',
        'players_decision',
        'judge_decision',
        'end_round',
        'ended',
    ]

    def __init__(self):
        # Load all the game statuses
        self.stahted = 'stahted'
        self.initiated = 'initiated'
        self.players_decision = 'players_decision'
        self.judge_decision = 'judge_decision'
        self.end_round = 'end_round'
        self.ended = 'ended'
        self.current_status = self.stahted


class Game:
    """Holds data for current game"""
    def __init__(self, players, deck, trigger_msg):
        self.bkb = BlockKitBuilder()
        self.game_id = id(datetime.now().timestamp())
        self.players = Players(players, origin='prebuilt')
        shuffle(self.players.player_list)
        self.judge_order = self.get_judge_order()
        self.judge = self.players.player_list[0]
        self.prev_judge = None
        self.game_start_time = self.round_start_time = datetime.now()
        # Used to start up a similar game in case of this game failing
        self.trigger_msg = trigger_msg
        # Starting number of cards for each player
        self.DECK_SIZE = 5
        self.deck = deck
        self.ping_judge = True
        self.ping_winner = True
        self.picks = None
        self.prev_question_card = None
        self.current_question_card = None
        self.rounds = 0
        self.gs = GameStatus()
        self.status = self.gs.current_status
        self._new_game()

    def get_judge_order(self):
        """Determines order of judges """
        order = ' :finger-wag-right: '.join([x.display_name for x in self.players.player_list])
        return f'Judge order: {order}'

    def _new_game(self):
        """Begin new game"""

        # Shuffle deck
        self.deck.shuffle_deck()
        # Set status as initiated
        self.status = self.gs.initiated

    def new_round(self):
        """Starts a new round"""

        if self.status not in [self.gs.end_round, self.gs.initiated]:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'Cannot transition to new round due to current status (`{self.status}`)')

        # Determine if the game should be ended before proceeding
        if len(self.deck.questions_card_list) == 0:
            # No more questions, game hath ended
            self.end_game()
            return [self.bkb.make_block_section(f'No more question cards! Game over! {":party-dead:" * 3}')]

        # Increment rounds
        self.rounds += 1

        # Get new judge
        self.get_next_judge()

        # Determine number of cards to deal to each player & deal
        # either full deck or replacement cards for previous question
        if self.rounds == 1:
            num_cards = self.DECK_SIZE
        else:
            self.prev_question_card = self.current_question_card
            num_cards = self.prev_question_card.required_answers
        self.deal_cards(num_cards)
        # Set picks back to none
        for player in self.players.player_list:
            player.hand.picks = None
            player.new_hand = False
            self.players.update_player(player)
        self.status = self.gs.players_decision

        # Deal question card
        self.current_question_card = self.deck.deal_question_card()

        self.round_start_time = datetime.now()

    def end_game(self):
        """Ends the game"""
        self.status = self.gs.ended
        # Save game scores
        for player in self.players.player_list:
            player.final_scores.append(player.points)
            player.points = 0
            self.players.update_player(player)

    def get_next_judge(self):
        """Gets the following judge by the order set"""
        self.prev_judge = self.judge
        cur_judge_pos = self.players.get_player_index_by_id(self.judge.player_id)
        next_judge_pos = 0 if cur_judge_pos == len(self.players.player_list) - 1 else cur_judge_pos + 1
        self.judge = self.players.player_list[next_judge_pos]

    def deal_cards(self, num_cards):
        """Deals cards out to players by indicating the number of cards to give out"""

        for player in self.players.player_list:
            if num_cards == self.DECK_SIZE:
                # At the first round of the game, everyone gets cards
                self._card_dealer(player, num_cards)
            elif player.player_id != self.prev_judge.player_id:
                # Otherwise, we'll make sure the judge doesn't get dealt an extra card
                self._card_dealer(player, num_cards)

    def _card_dealer(self, player_obj, num_cards):
        """Deals the actual cards"""
        for i in range(0, num_cards):
            # Distribute cards
            if len(self.deck.answers_card_list) == 0:
                return 'No more cards left to deal!'
            else:
                player_obj.hand.take_card(self.deck.deal_answer_card())
        self.players.update_player(player_obj)

    def assign_player_pick(self, user_id, picks):
        """Takes in an int and assigns it to the player who wrote it"""
        player = self.players.get_player_by_id(user_id)
        success = player.hand.pick_card(picks)
        if success:
            self.players.update_player(player)
            return f'{player.display_name}\'s pick has been registered.'
        elif not success and player.hand.picks is not None:
            return f'{player.display_name}\'s pick voided. You already picked.'
        else:
            return 'Pick not registered.'

    def players_left_to_decide(self):
        """Returns a list of the players that have yet to pick a card"""

        remaining = []
        for player in self.players.player_list:
            if player.hand.picks is None and player.player_id != self.judge.player_id:
                remaining.append(player.display_name)
        return remaining

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self.ping_judge = not self.ping_judge

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        self.ping_winner = not self.ping_winner

    def display_picks(self):
        """Shows the player's picks in random order"""

        picks = [{'id': player.player_id, 'picks': [x.txt for x in player.hand.picks]}
                 for player in self.players.player_list if player.hand.picks is not None]
        shuffle(picks)
        self.picks = picks

        card_blocks = []
        btn_list = []  # Button info to be made into a button group
        randbtn_list = []  # Just like above, but bear a 'rand' prefix to differentiate. These can be subset.
        for i, picks in enumerate(self.picks):
            num = i + 1
            card_blocks.append(self.bkb.make_block_section(
                f'*{num}*: {"|".join([f" *`{x}`* " for x in picks["picks"]])}'))

            btn_list.append({'txt': f'{num}', 'value': f'choose-{num}'})
            randbtn_list.append({'txt': f'{num}', 'value': f'randchoose-{num}'})

        definite_selection_area = self.bkb.make_button_group(btn_list)

        rand_options = [{'txt': 'All choices', 'value': 'randchoose-all'}] + randbtn_list

        return card_blocks + [
            self.bkb.make_block_divider(),
            definite_selection_area,
            self.bkb.make_block_divider(),
            self.bkb.make_block_multiselect('Randchoose (all or subset)', 'Select choices', rand_options)
        ]
