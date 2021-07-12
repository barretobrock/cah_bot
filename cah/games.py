#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List, Optional, Tuple, Union, Dict
from datetime import datetime
from random import shuffle, choice
import numpy as np
from sqlalchemy.sql import func, and_
from slacktools import BlockKitBuilder as bkb
from slack.errors import SlackApiError
from easylogger import Log
import cah.app as cah_app
import cah.cards as cards
from .players import Players, Player, Judge
from .model import TableGames, TableGameRounds, TableGameSettings, GameStatuses, TablePlayerRounds, TablePlayers
from .settings import auto_config


# Define statuses where game is not active
game_not_active = [GameStatuses.initiated, GameStatuses.ended]
# Status when ready to transition into new round
new_round_ready = [GameStatuses.initiated, GameStatuses.end_round]

DECK_SIZE = 5


class Game:
    """Holds data for current game"""
    def __init__(self, players: List[str], deck: cards.Deck, parent_log: Log):
        self.st = cah_app.Bot.st
        self.log = Log(parent_log, child_name=self.__class__.__name__)
        self.log.debug('Building out new game...')

        # Database table links
        # Create a new game
        self.status = GameStatuses.initiated
        game_tbl = TableGames()  # type: TableGames
        cah_app.db.session.add(game_tbl)
        cah_app.db.session.commit()
        self.game_id = game_tbl.id

        game_settings_tbl = self._get_game_settings_tbl()
        self._is_ping_judge = game_settings_tbl.is_ping_judge
        self._is_ping_winner = game_settings_tbl.is_ping_winner
        self._decknuke_penalty = game_settings_tbl.decknuke_penalty
        # This one will be set when new_round() is called
        self.gameround_id = None

        self.players = Players(players, slack_api=self.st, parent_log=self.log)
        shuffle(self.players.player_list)
        self.judge_order = self.get_judge_order()
        _judge = self.players.player_list[0]
        self.judge = Judge(_judge)    # type: Judge
        self.prev_judge = None
        self.game_start_time = self.round_start_time = datetime.now()

        self.deck = deck

        self.round_picks = []
        self.round_ts = None  # Stores the timestamp of the question card message for the round
        self.prev_question_card = None      # type: Optional[cards.QuestionCard]
        self.current_question_card = None   # type: Optional[cards.QuestionCard]

        self.deck.shuffle_deck()

    @property
    def is_ping_judge(self):
        return self._is_ping_judge

    @is_ping_judge.setter
    def is_ping_judge(self, value):
        self._is_ping_judge = value
        tbl = self._get_game_settings_tbl()
        tbl.is_ping_judge = self._is_ping_judge
        cah_app.db.session.commit()

    @property
    def decknuke_penalty(self):
        return self._decknuke_penalty

    @decknuke_penalty.setter
    def decknuke_penalty(self, value):
        self._decknuke_penalty = value
        tbl = self._get_game_settings_tbl()
        tbl.decknuke_penalty = self._decknuke_penalty
        cah_app.db.session.commit()

    @property
    def is_ping_winner(self):
        return self._is_ping_winner

    @is_ping_winner.setter
    def is_ping_winner(self, value):
        self._is_ping_winner = value
        tbl = self._get_game_settings_tbl()
        tbl.is_ping_winner = self._is_ping_winner
        cah_app.db.session.commit()

    @property
    def round_number(self) -> int:
        """Retrieves the round number from the db"""
        game_tbl = self._get_game_tbl()
        return len(game_tbl.rounds)

    def _get_game_settings_tbl(self) -> TableGameSettings:
        """Attempts to retrieve the gamesettings tbl. If it doesn't exist, will make a new one and commit it"""
        # Bring in the settings
        game_settings_tbl = cah_app.db.session.query(TableGameSettings).one_or_none()
        if game_settings_tbl is None:
            # No table found... make a new one
            self.log.debug('Game settings table not found. Making a new one.')
            game_settings_tbl = TableGameSettings()
        return game_settings_tbl

    def _get_game_tbl(self) -> TableGames:
        """Attempts to retrieve the game tbl."""
        game_tbl = cah_app.db.session.query(TableGames).filter(TableGames.id == self.game_id).one_or_none()
        return game_tbl

    def _get_gameround_tbl(self) -> TableGameRounds:
        """Attempts to retrieve the game tbl."""
        gameround_tbl = cah_app.db.session.query(TableGameRounds).join(TableGames)\
            .filter(and_(
                TableGames.id == self.game_id,
                TableGameRounds.id == self.gameround_id
            )).one_or_none()
        return gameround_tbl

    def get_judge_order(self) -> str:
        """Determines order of judges """
        game_settings_tbl = self._get_game_settings_tbl()
        order_divider = game_settings_tbl.judge_order_divider
        order = f' {order_divider} '.join(self.players.get_player_names(monospace=True))
        return f'Judge order: {order}'

    def new_round(self, notification_block: List[Dict] = None) -> Optional[List[dict]]:
        """Starts a new round"""

        if self.status not in new_round_ready:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'Cannot transition to new round due to current status '
                             f'(`{self.status.name}`)')

        if self.round_number > 0:
            # Not the first round...
            self.end_round()

        # Determine if the game should be ended before proceeding
        if len(self.deck.questions_card_list) == 0:
            # No more questions, game hath ended
            self.end_game()
            return [bkb.make_block_section(f'No more question cards! Game over! {":party-dead:" * 3}')]

        if notification_block is None:
            notification_block = []

        self.round_start_time = datetime.now()
        gameround = TableGameRounds(game_id=self.game_id)
        cah_app.db.session.add(gameround)
        cah_app.db.session.commit()
        self.gameround_id = gameround.id
        round_number = self.round_number

        lines = '=' * 32
        self.log.debug(f'\n{lines}\n\t\tROUND {round_number} STARTED ({self.gameround_id})\n{lines}')

        # Reset the round timestamp (used to keep track of the main round message in channel)
        self.round_ts = None

        # Prep player list for new round
        self.players.new_round(game_id=self.game_id, round_id=self.gameround_id)

        # Get new judge if not the first round. Mark judge as such in the db
        self.get_next_judge(n_round=round_number, game_id=self.game_id, round_id=self.gameround_id)

        # Determine number of cards to deal to each player & deal
        # either full deck or replacement cards for previous question
        if self.round_number > 1:
            self.prev_question_card = self.current_question_card
        self.deal_cards()

        cah_app.db.session.commit()

        self.status = GameStatuses.players_decision

        # Deal question card
        self.current_question_card = self.deck.deal_question_card()

        self.st.private_channel_message(self.judge.player_id, auto_config.MAIN_CHANNEL,
                                        ":gavel::gavel::gavel: You're the judge this round! :gavel::gavel::gavel:")
        question_block = self.make_question_block()
        notification_block += question_block
        self.st.message_test_channel(blocks=notification_block)
        self.handle_render_hands()

    def end_round(self):
        """Procedures for ending the round"""
        self.log.debug('Ending round.')
        # Update the previous round with an end time
        gameround = self._get_gameround_tbl()
        gameround.end_time = datetime.utcnow()
        cah_app.db.session.commit()
        self.status = GameStatuses.end_round

    def end_game(self):
        """Ends the game"""
        self.log.debug('End game process started')
        if self.status is game_not_active:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'No active game to end - status: (`{self.status.name}`)')
        self.end_round()
        game_tbl = self._get_game_tbl()
        game_tbl.end_time = datetime.utcnow()
        self.status = GameStatuses.ended
        cah_app.db.session.commit()

    def handle_render_hands(self):
        # Get the required number of answers for the current question
        self.log.debug('Rendering hands process beginning.')
        req_ans = self.current_question_card.required_answers
        question_block = self.make_question_block()
        try:
            self.players.render_hands(judge_id=self.judge.player_id, question_block=question_block,
                                      req_ans=req_ans)
        except cards.OutOfCardsException:
            self.log.debug('Stopping game - ran out of cards!')
            blocks = [bkb.make_block_section(f'The people have run out of answer cards! Game over! '
                                             f'{":party-dead:" * 3}')]
            self.st.message_test_channel(blocks=blocks)
            self.end_game()
            return None
        # Determine randpick players and pick for them
        for player in self.players.player_list:
            if player.player_id == self.judge.player_id:
                continue
            if player.is_arp:
                # Player has elected to automatically pick their cards
                self.process_picks(player.player_id, 'randpick')
                if player.is_dm_cards:
                    self.st.private_message(player.player_id, 'Your pick was handled automatically, '
                                                              'as you have `auto randpick` enabled.')

    def get_next_judge(self, n_round: int, game_id: int, round_id: int):
        """Gets the following judge by the order set"""
        self.log.debug('Determining judge.')
        if n_round > 1:
            # Rotate judge
            self.prev_judge = self.judge
            cur_judge_pos = self.players.get_player_index(self.judge.player_id)
            self.players.player_list[cur_judge_pos].is_judge = False
            next_judge_pos = 0 if cur_judge_pos == len(self.players.player_list) - 1 else cur_judge_pos + 1
            _judge = self.players.player_list[next_judge_pos]
            self.judge = Judge(_judge)
        self.judge.game_id = game_id
        self.judge.round_id = round_id
        self.judge.is_judge = True

    def _deal_card(self):
        if len(self.deck.answers_card_list) == 0:
            self.log.debug('No more cards left to deal!!!!!')
            return None
        return self.deck.deal_answer_card()

    def deal_cards(self):
        """Deals cards out to players by indicating the number of cards to give out"""
        for player in self.players.player_list:
            if self.deck.num_answer_cards == 0:
                break
            if self.round_number > 1 and self.judge.player_id == player.player_id:
                # Skip judge if dealing after first round
                continue
            if player.hand.get_num_cards() == DECK_SIZE:
                continue
            num_cards = DECK_SIZE - player.hand.get_num_cards()
            if num_cards > 0:
                self.log.debug(f'Dealing {num_cards} cards to {player.display_name}')
                card_list = [self._deal_card() for _ in range(num_cards)]
                self.players.take_dealt_cards(player, card_list=card_list)
                self.log.debug(f'Player {player.display_name} now has {player.hand.get_num_cards()} cards')
            else:
                self.log.warning(f'Player {player.display_name} now has {player.hand.get_num_cards()} cards')

    def decknuke(self, player_id: str):
        player = self.players.get_player(player_attr=player_id, attr_name='player_id')
        self.log.debug(f'Player {player.display_name} has nuked their deck. Processing command.')
        if self.judge.player_id == player.player_id:
            self.st.message_test_channel(f'Decknuke rejected. {player.player_tag} is the judge. :shame:')
            return
        # Randpick a card for this user
        if player.hand.get_num_cards() < self.current_question_card.required_answers:
            self.st.message_test_channel(f'Decknuke rejected. {player.player_tag} ran out of cahds. :shame:')
            self.end_game()
            return
        self.process_picks(player_id, 'randpick')
        # Remove all cards form their hand & tag player
        self.players.process_player_decknuke(player)
        addl_txt = '...also, we\'re out of cards hehe..' if self.deck.num_answer_cards == 0 else ''
        self.st.message_test_channel(f'{player.player_tag} nuked their deck! :frogsiren: {addl_txt}')
        # Deal the player the unused new cards the number of cards played will be replaced after the round ends.
        n_cards = DECK_SIZE - self.current_question_card.required_answers
        card_list = [self._deal_card() for _ in range(n_cards)]
        self.players.take_dealt_cards(player, card_list=card_list)

    def get_current_scores(self) -> List[TablePlayers]:
        """Gets the current scores of the ongoing game"""
        self.log.debug('Retrieving current player scores from database')
        return cah_app.db.session.query(
            TablePlayers.id,
            TablePlayers.name,
            func.sum(TablePlayerRounds.score).label('diddles')
            ).join(TablePlayers, TablePlayerRounds.player_id == TablePlayers.id) \
            .filter(TablePlayerRounds.game_id == self.game_id) \
            .group_by(TablePlayers.id).all()

    def round_wrap_up(self):
        """Coordinates end-of-round logic (tallying votes, picking winner, etc.)"""
        # Make sure all users have votes and judge has made decision before wrapping up the round
        # Handle the announcement of winner and distribution of points
        self.st.message_test_channel(blocks=self.winner_selection())
        self.status = GameStatuses.end_round
        # Start new round
        self.new_round()

    def winner_selection(self) -> List[dict]:
        """Contains the logic that determines point distributions upon selection of a winner"""
        # Get the list of cards picked by each player
        self.log.debug(f'Selecting winner at index: {self.judge.pick_idx}')
        rps = self.round_picks
        winning_pick = rps[self.judge.pick_idx]     # type: cards.Pick

        # Winner selection
        winner = self.players.get_player(winning_pick.owner_id)
        winner_was_none = winner is None
        if winner is None:
            # Likely the player who won left the game. Add to their overall points
            self.log.debug(f'The winner selected seems to have left the game. Spinning their object up to '
                           f'grant their points.')
            # Get the winner from the master list of the players
            winner_tbl = cah_app.db.session.query(TablePlayers)\
                .filter(TablePlayers.slack_id == winning_pick.owner_id).one_or_none()
            # Load the winner object
            winner = Player(winner_tbl.slack_id, display_name=winner_tbl.name)
            # Attach the current round to the winner
            winner.game_id = self.game_id
            winner.round_id = self.gameround_id
            # Attaching winning pick to winner's hand
            winner.hand.pick = winning_pick

        self.log.debug(f'Winner selected as {winner.display_name}')
        # If decknuke occurred, distribute the points to others randomly
        if winner.is_nuked_hand:
            penalty = self.decknuke_penalty
            point_receivers_txt = self._points_redistributer(penalty)
            points_won = penalty
            decknuke_txt = f'\n:impact::impact::impact::impact:LOLOLOLOLOL HOW DAT DECKNUKE WORK FOR YA NOW??\n' \
                           f'Your points were redistributed such: {point_receivers_txt}'
            winner.is_nuked_hand_caught = True
            cah_app.db.session.commit()
        else:
            points_won = 1
            decknuke_txt = ''

        # Mark card as chosen in db
        self.log.debug('Marking chosen card(s) in db.')
        winner.hand.mark_chosen_pick()

        winner.add_points(points_won)
        if not winner_was_none:
            self.players._update_player(winner)
        winner_details = winner.player_tag if self.is_ping_winner else f'*`{winner.display_name.title()}`*'
        winner_txt_blob = [
            f":regional_indicator_q: *{self.current_question_card.txt}*",
            f":tada:Winning card: {winner.hand.pick.render_pick_list_as_str()}",
            f"*`{points_won:+}`* :diddlecoin: to {winner_details}! "
            f"New score: *`{winner.get_current_score(game_id=self.game_id)}`* :diddlecoin: "
            f"({winner.get_overall_score()} total){decknuke_txt}\n"
        ]
        last_section = [
            bkb.make_context_section([
                bkb.markdown_section(f'Round ended. Nice going, {self.judge.display_name}.')
            ])
        ]

        message_block = [
            bkb.make_block_section(winner_txt_blob),
            bkb.make_block_divider(),
        ]
        return message_block + last_section

    def _points_redistributer(self, penalty: int) -> str:
        """Handles the logic covering redistribution of wealth among players"""
        self.log.debug('Redistributing points post discovered decknuke')
        # Deduct points from the judge, give randomly to others
        point_receivers = {}  # Store 'name' (of player) and 'points' (distributed)
        # Determine the eligible receivers of the extra points
        nonjudge_players = [x for x in self.players.player_list if x.player_id != self.judge.player_id]
        player_points_list = [x.get_current_score(game_id=self.game_id) for x in nonjudge_players]
        eligible_receivers = [x for x in nonjudge_players]
        # Some people have earned points already. Make sure those with the highest points aren't eligible
        max_points = max(player_points_list)
        min_points = min(player_points_list)
        if max_points - min_points > 3:
            eligible_receivers = [x for x in nonjudge_players
                                  if x.get_current_score(game_id=self.game_id) < max_points]
        for pt in range(0, penalty * -1):
            if len(eligible_receivers) > 1:
                player = list(np.random.choice(eligible_receivers, 1))[0]
            elif len(eligible_receivers) == 1:
                # In case everyone has the max score except for one person
                player = eligible_receivers[0]
            else:
                # Everyone has the same score lol. Just pick a random player
                player = list(np.random.choice(nonjudge_players, 1))[0]

            player.add_points(1)
            # Record the points for notifying in the channel
            if player.player_id in point_receivers.keys():
                # Add another point
                point_receivers[player.player_id]['points'] += 1
            else:
                point_receivers[player.player_id] = {
                    'name': player.display_name,
                    'points': 1
                }
            self.players._update_player(player)
        point_receivers_txt = '\n'.join([f'`{v["name"]}`: *`{v["points"]}`* :diddlecoin:'
                                         for k, v in point_receivers.items()])
        return point_receivers_txt

    def replace_block_forms(self, player: Player):
        """Replaces the Block UI form with another message"""
        blk = [
            bkb.make_block_section(f'Your pick(s): {player.hand.pick.render_pick_list_as_str()}')
        ]
        replace_blocks = player.pick_blocks
        for chan, ts in replace_blocks.items():
            if chan[0] == 'C':
                # Ephemeral message - delete it, as it can't be updated
                try:
                    # This only posts if the person is active at time of distribution
                    self.st.delete_message(channel=chan, ts=ts)
                except SlackApiError:
                    # Bypass this error - ephemeral message not found
                    pass
            else:
                # DM - update it
                self.st.update_message(chan, ts, blocks=blk)
        # Reset the blocks
        self.players.reset_player_pick_block(player_obj=player)

    def assign_player_pick(self, user_id: str, picks: List[int]) -> str:
        """Takes in an int and assigns it to the player who wrote it"""
        player = self.players.get_player(player_attr=user_id, attr_name='player_id')
        self.log.debug(f'Assigning pick to player {player.display_name}')
        success = player.hand.pick_card(picks)
        if success:
            # Replace the pick messages
            self.log.debug('Pick assignment successful. Updating player.')
            self.players._update_player(player)
            self.replace_block_forms(player)
            return f'*`{player.display_name}`*\'s pick has been registered.'
        elif not success and not player.hand.pick.is_empty():
            return f'*`{player.display_name}`*\'s pick voided. You already picked.'
        else:
            return 'Pick not registered.'

    def players_left_to_pick(self) -> List[str]:
        """Returns a list of the players that have yet to pick a card"""
        self.log.debug('Determining players remaining to pick')
        remaining = []
        for player in self.players.player_list:
            if player.hand.pick.is_empty() and player.player_id != self.judge.player_id:
                remaining.append(player.display_name)
        return remaining

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self.log.debug('Toggling judge pinging')
        self.is_ping_judge = not self.is_ping_judge

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        self.log.debug('Toggling winner pinging')
        self.is_ping_winner = not self.is_ping_winner

    def process_picks(self, user: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        self.log.debug(f'Received pick message: {message}')
        # We're in the right status and the user isn't a judge. Let's break this down further
        card_subset = None  # For when player wants to pick from a subset
        msg_split = message.split()

        # Set the player as the user first, but see if the user is actually picking for someone else
        player = self.players.get_player(player_attr=user, attr_name='player_id')
        if any(['<@' in x for x in msg_split]):
            # Player has tagged someone. See if they tagged themselves or another person
            if not any([player.player_tag in x for x in msg_split]):
                # Tagged someone else. Get that other tag & use it to change the player.
                ptag = next((x for x in msg_split if '<@' in x))
                player = self.players.get_player(player_attr=ptag.upper(), attr_name='player_tag')

        # Make sure the player referenced isn't the judge
        if player.player_id == self.judge.player_id:
            self.st.message_test_channel(f'{player.player_tag} is the judge this round. Judges can\'t pick!')
            return None

        # Player is set, now determine what we need to do
        if 'randpick' in message:
            # Random picking section
            n_cards = len(player.hand.cards)
            req_ans = self.current_question_card.required_answers
            if len(msg_split) > 1:
                # Randpick possibly includes further instructions
                after_randpick = msg_split[1]
                if '<@' not in after_randpick:
                    # This was not a tag;
                    if after_randpick.isnumeric():
                        card_subset = list(map(int, list(after_randpick)))
                    elif ',' in after_randpick:
                        card_subset = list(map(int, after_randpick.split(',')))
                    else:
                        # Pick not understood; doesn't match expected syntax
                        self.st.message_test_channel(
                            f'<@{user}> I didn\'t understand your randpick message (`{message}`). Pick voided.')
                        return None
                else:
                    # Was a tag. We've already applied the tag earlier
                    pass
            else:
                # Just 'randpick'
                pass
            # Determine how we're gonna randpick
            if card_subset is not None:
                # Player wants to randomly choose from a subset of cards
                # Check that the subset is at least the same number as the required cards
                if len(card_subset) >= req_ans:
                    picks = [x - 1 for x in np.random.choice(card_subset, req_ans, False).tolist()]
                else:
                    self.st.message_test_channel(f'<@{user}> your subset of picks is too small. '
                                                 f'At least (`{req_ans}`) picks required. Pick voided.')
                    return None
            else:
                # Randomly choose over all of the player's cards
                picks = np.random.choice(n_cards, req_ans, False).tolist()

        else:
            # Performing a standard pick; process the pick from the message
            picks = self._get_pick(user, message)

        if picks is None:
            return None
        elif any([x > len(player.hand.cards) - 1 or x < 0 for x in picks]):
            self.st.message_test_channel(f'<@{user}> I think you picked outside the range of suggestions. '
                                         f'Your picks: `{picks}`.')
            return None
        messages = [self.assign_player_pick(player.player_id, picks)]

        if player.is_dm_cards and 'randpick' in message:
            # Ping player their randomly selected picks if they've chosen to be DMed cards
            self.st.private_message(player.player_id, f'Your randomly selected pick(s): '
                                                      f'{player.hand.pick.render_pick_list_as_str()}')

        # See who else has yet to decide
        remaining = self.players_left_to_pick()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.is_ping_judge:
                judge_msg = f'{self.judge.player_tag} to judge.'
            else:
                judge_msg = f'`{self.judge.display_name.title()}` to judge.'
            messages.append(judge_msg)
            self.status = GameStatuses.judge_decision
            # Update the "remaining picks" message
            self.st.update_message(auto_config.MAIN_CHANNEL, self.round_ts, message='we gone')
            self._display_picks(notifications=messages)
            # Handle auto randchoose players
            if self.judge.is_arc:
                # Judge only
                self.choose_card(player.player_id, 'randchoose')
        else:
            # Make the remaining players more visible
            remaining_txt = ' '.join([f'`{x}`' for x in remaining])
            messages.append(f'*`{len(remaining)}`* players remaining to decide: {remaining_txt}')
            msg_block = [bkb.make_context_section([bkb.markdown_section(x) for x in messages])]
            if self.round_ts is None:
                # Announcing the picks for the first time; capture the timestamp so
                #   we can update that same message later
                self.round_ts = self.st.send_message(auto_config.MAIN_CHANNEL, message='', ret_ts=True,
                                                     blocks=msg_block)
            else:
                # Update the message we've already got
                self.st.update_message(auto_config.MAIN_CHANNEL, self.round_ts, blocks=msg_block)

    def _get_pick(self, user: str, message: str, judge_decide: bool = False) -> Union[int, Optional[List[int]]]:
        """Processes a number from a message"""
        self.log.debug(f'Extracting pick from message: {message}')

        def isolate_pick(pick_txt: str) -> Optional[List[int]]:
            if ',' in pick_txt:
                return [int(x) for x in pick_txt.split(',') if x.isnumeric()]
            elif pick_txt.isnumeric():
                return [int(x) for x in list(pick_txt)]
            return None

        # Process the message
        msg_split = message.split()
        picks = None
        if len(msg_split) == 2:
            # Our pick was something like 'pick 4', 'pick 42' or 'pick 3,2'
            pick_part = msg_split[1]
            picks = isolate_pick(pick_part)
        elif len(msg_split) > 2:
            # Our pick was something like 'pick 4 2' or 'pick 3, 2'
            pick_part = ''.join(msg_split[1:])
            picks = isolate_pick(pick_part)

        if picks is None:
            self.st.message_test_channel(f'<@{user}> - I didn\'t understand your pick. You entered: `{message}` \n'
                                         f'Try something like `p 12` or `pick 2`')
        elif judge_decide:
            if len(picks) == 1:
                # Expected number of picks for judge
                return picks[0] - 1
            else:
                self.st.message_test_channel(f'<@{user}> - You\'re the judge. '
                                             f'You should be choosing only one set. Try again!')
        else:
            # Confirm that the number of picks matches the required number of answers
            req_ans = self.current_question_card.required_answers
            if len(set(picks)) == req_ans:
                # Set picks to 0-based index and send onward
                return [x - 1 for x in picks]
            else:
                self.st.message_test_channel(f'<@{user}> - You chose {len(picks)} things, '
                                             f'but the current question requires {req_ans}.')
        return None

    def _display_picks(self, notifications: List[str] = None):
        """Shows a random order of the picks"""
        if notifications is not None:
            public_response_block = [
                bkb.make_context_section([bkb.markdown_section(x) for x in notifications]),
                bkb.make_block_divider()
            ]
        else:
            public_response_block = []
        question_block = self.make_question_block()
        public_choices, private_choices = self.display_picks()
        public_response_block += question_block + public_choices
        # Judge's block
        judge_response_block = question_block + private_choices
        # Show everyone's picks to the group, but only send the choice buttons to the judge
        self.st.message_test_channel(blocks=public_response_block)

        # Handle sending judge messages
        # send as private in-channel message (though this sometimes goes unrendered)
        pchan_ts = self.st.private_channel_message(self.judge.player_id, auto_config.MAIN_CHANNEL,
                                                   message='', ret_ts=True, blocks=judge_response_block)
        if self.judge.is_dm_cards:
            # DM choices to player if they have card dming enabled
            dm_chan, ts = self.st.private_message(self.judge.player_id, message='', ret_ts=True,
                                                  blocks=judge_response_block)

    def display_picks(self) -> Tuple[List[dict], List[dict]]:
        """Shows the player's picks in random order"""
        self.log.debug('Rendering picks...')
        picks = [player.hand.pick for player in self.players.player_list if not player.hand.pick.is_empty()]
        shuffle(picks)
        self.round_picks = picks

        judge_card_blocks = []
        public_card_blocks = []
        randbtn_list = []  # Just like above, but bear a 'rand' prefix to differentiate. These can be subset.
        for i, round_pick in enumerate(self.round_picks):
            num = i + 1
            # Make a block specifically for the judge (with buttons)
            card_btn_dict = bkb.make_action_button(f'{num}', f'choose-{num}', action_id=f'game-choose-{num}')
            pick_txt = f'*{num}*: {"|".join([f" *`{x}`* " for x in round_pick.pick_txt_list])}'
            judge_card_blocks.append(bkb.make_block_section(pick_txt, accessory=card_btn_dict))
            # Make a "public" block that just shows the choices in the channel
            public_card_blocks.append(bkb.make_block_section(pick_txt))
            randbtn_list.append({'txt': f'{num}', 'value': f'randchoose-{num}'})

        rand_options = [{'txt': 'All choices', 'value': 'randchoose-all'}] + randbtn_list

        return public_card_blocks, judge_card_blocks + [
            bkb.make_block_divider(),
            bkb.make_block_multiselect('Randchoose (all or subset)', 'Select choices', rand_options),
            bkb.make_block_section('Force Close', accessory=bkb.make_action_button('Close', 'none',
                                                                                   action_id='close'))
        ]

    def make_question_block(self) -> List[dict]:
        """Generates the question block for the current round"""
        # Determine honorific for judge
        self.log.debug('Determining honorific for judge...')
        # Honorifics will be chosen based on which range of points the judge falls into
        honorifics = {
            range(-200, -6): ['loser', 'toady', 'weak', 'despised', 'defeated', 'under-under-underdog'],
            range(-6, -3): ['concerned', 'bestumbled', 'under-underdog'],
            range(-3, 0): ['temporarily disposed', 'momentarily disheveled', 'underdog'],
            range(0, 3): ['lackey', 'intern', 'doormat', 'underling', 'deputy', 'amateur', 'newcomer'],
            range(3, 6): ['young padawan', 'master apprentice', 'rookie', 'greenhorn', 'fledgling', 'tenderfoot'],
            range(6, 9): ['honorable', 'respected and just', 'cold and yet still fair'],
            range(9, 12): ['worthy inheriter of (mo|da)ddy\'s millions', '(mo|fa)ther of dragons',
                           'most excellent', 'knowledgeable', 'wise'],
            range(12, 15): ['elder', 'ruler of the lower cards', 'most fair dictator of difficult choices'],
            range(15, 18): ['benevolent and omniscient chief of dutiful diddling', 'supreme high chancellor of '],
            range(18, 21): ['almighty veteran diddler', 'ancient diddle dealer from before time began',
                            'sage of the diddles'],
            range(21, 500): ['bediddled', 'grand bediddler', 'most wise in the ways of the diddling',
                             'pansophical bediddled sage of the dark cards']
        }

        judge_pts = self.judge.get_current_score(game_id=self.game_id)
        judge_pts = judge_pts if judge_pts is not None else 0
        # Determine the subset of honorifics to use
        honorific_list = honorifics[range(0, 3)]
        for k, v in honorifics.items():
            if judge_pts in k:
                honorific_list = v
                break

        honorific = f'the {choice(honorific_list)}'

        # Assign this to the judge so we can refer to it in other areas.
        self.judge.honorific = honorific.title()
        cah_app.db.session.commit()
        bot_moji = ':math:' if self.judge.is_arc else ''

        return [
            bkb.make_block_section(
                f'Round *`{self.round_number}`* - *{self.judge.honorific} '
                f'Judge {self.judge.display_name.title()}* {bot_moji} presiding.'
            ),
            bkb.make_block_section(
                f'*:regional_indicator_q:: {self.current_question_card.txt}*'
            ),
            bkb.make_block_divider()
        ]

    def choose_card(self, user: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""
        self.log.debug(f'Choose command used: {message}')
        if user in auto_config.ADMINS and 'blueberry pie' in message:
            # Overrides the block below to allow admin to make a choice during testing or special circumstances
            user = self.judge.player_id
            message = 'randchoose'

        used_randchoose = 'randchoose' in message

        # Whether the player used randchoose over all the cards (disqualifies from voting)
        if used_randchoose:
            pick, used_all = self._randchoose_handling(message)
            if pick is None:
                # The randchoose method wasn't able to parse anything useful from the message
                self.log.error('Pick returned None: randchoose seemed to fail to pick something.')
                return None
        else:
            self.log.debug('Extracting judge\'s pick from message')
            pick = self._get_pick(user, message, judge_decide=True)

        if pick > len(self.players.player_list) - 2 or pick < 0:
            self.log.debug(f'Chosen pick ({pick}) was outside of spec.')
            # Pick is rendered as an array index here.
            # Pick can either be:
            #   -less than total players minus judge, minus 1 more to account for array
            #   -greater than -1
            self.st.message_test_channel(f'I think you picked outside the range of suggestions. '
                                         f'Your pick: {pick}')
            return None
        else:
            if user == self.judge.player_id:
                # Record the judge's pick
                if self.judge.pick_idx is None:
                    self.log.debug(f'Setting judge\'s pick as {pick}:')
                    self.judge.pick_idx = pick
                else:
                    self.st.message_test_channel('Judge\'s pick voided. You\'ve already picked this round.')

    def _randchoose_handling(self, message: str) -> Optional[Tuple[int, bool]]:
        """Contains all the logic for handling a randchoose command"""
        self.log.debug(f'Randchoose command used: {message}')
        used_all = False
        if len(message.split(' ')) > 1:
            randchoose_instructions = message.split(' ')[1]
            # Use a subset of choices
            card_subset = None
            if randchoose_instructions.isnumeric():
                card_subset = list(map(int, list(randchoose_instructions)))
            elif ',' in randchoose_instructions:
                card_subset = list(map(int, randchoose_instructions.split(',')))
            if card_subset is not None:
                # Pick from the card subset and subtract by 1 to bring it in line with 0-based index
                pick = list(np.random.choice(card_subset, 1))[0] - 1
            else:
                # Card subset wasn't able to be parsed
                self.st.message_test_channel('I wasn\'t able to parse the card subset you entered. '
                                             'Try again!')
                return None
        else:
            # Randomly choose from all cards
            # available choices = total number of players - (judge + len factor)
            used_all = True
            available_choices = len(self.players.player_list) - 2
            if available_choices == 0:
                pick = 0
            else:
                pick = list(np.random.choice(available_choices, 1))[0]
        return pick, used_all
