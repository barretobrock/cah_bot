#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List, Optional, Tuple, Union
from datetime import datetime
from random import shuffle
import numpy as np
from sqlalchemy.sql import and_, func
from sqlalchemy.orm.session import Session
from slacktools import BlockKitBuilder as bkb
from slack.errors import SlackApiError
from easylogger import Log
import cah.app as cah_app
from .players import Players, Player, Judge
from .model import TableGames, TableGameRounds, TableGameSettings, GameStatuses, TablePlayerRounds
from .db import get_session, auto_config


# Define statuses where game is not active
game_not_active = [GameStatuses.initiated, GameStatuses.ended]
# Status when ready to transition into new round
new_round_ready = [GameStatuses.initiated, GameStatuses.end_round]

DECK_SIZE = 5


class Game:
    """Holds data for current game"""
    def __init__(self, players: List[str], deck: 'Deck', parent_log: Log):
        self.st = cah_app.Bot.st
        self.log = Log(parent_log, child_name=self.__class__.__name__)
        self.session = get_session()      # type: Session

        # Database table links
        # Create a new game
        self.game_tbl = TableGames()  # type: TableGames
        self.session.add(self.game_tbl)
        # Bring in the settings
        self.game_settings_tbl = self.session.query(TableGameSettings).one_or_none()
        if self.game_settings_tbl is None:
            # No table found... make a new one
            self.game_settings_tbl = TableGameSettings()
            self.session.add(self.game_settings_tbl)
        self.session.commit()
        # This one will be set when new_round() is called
        self.gameround = None   # type: Optional[TableGameRounds]

        self.players = Players(players, session=self.session, slack_api=self.st, parent_log=self.log)
        shuffle(self.players.player_list)
        self.judge_order = self.get_judge_order()
        self.judge = self.players.player_list[0]    # type: Judge
        self.prev_judge = None
        self.game_start_time = self.round_start_time = datetime.now()

        self.deck = deck

        self.round_picks = []
        self.round_ts = None  # Stores the timestamp of the question card message for the round
        self.prev_question_card = None
        self.current_question_card = None

        self.deck.shuffle_deck()

    def get_judge_order(self) -> str:
        """Determines order of judges """
        order_divider = self.game_settings_tbl.judge_order_divider
        order = f' {order_divider} '.join(self.players.get_player_names(monospace=True))
        return f'Judge order: {order}'

    def end_round(self):
        """Procedures for ending the round"""
        # Update the previous round with an end time
        self.gameround.end_time = datetime.utcnow()
        self.game_tbl.status = GameStatuses.end_round
        self.session.commit()

    def new_round(self) -> Optional[List[dict]]:
        """Starts a new round"""

        if self.game_tbl.status not in new_round_ready:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'Cannot transition to new round due to current status '
                             f'(`{self.game_tbl.status.name}`)')

        if self.gameround is not None:
            # Not the first round...
            self.end_round()

        # Determine if the game should be ended before proceeding
        if len(self.deck.questions_card_list) == 0:
            # No more questions, game hath ended
            self.end_game()
            return [bkb.make_block_section(f'No more question cards! Game over! {":party-dead:" * 3}')]

        self.gameround = TableGameRounds(game_id=self.game_tbl.id)
        # Increment rounds
        self.game_tbl.rounds += 1

        # Get new judge if not the first round
        if self.game_tbl.rounds > 1:
            self.get_next_judge()
        # Reset the round timestamp
        self.round_ts = None

        # Prep player list for new round
        self.players.new_round(game_id=self.game_tbl.id, round_id=self.gameround.id)

        # Determine number of cards to deal to each player & deal
        # either full deck or replacement cards for previous question
        if self.game_tbl.rounds == 1:
            num_cards = DECK_SIZE
        else:
            self.prev_question_card = self.current_question_card
            num_cards = self.prev_question_card.required_answers
        self.deal_cards(num_cards)

        self.game_tbl.status = GameStatuses.players_decision

        # Deal question card
        self.current_question_card = self.deck.deal_question_card()

        self.gameround = TableGameRounds(game_id=self.game_tbl.id)

        self.session.commit()

    def end_game(self):
        """Ends the game"""
        if self.game_tbl.status is game_not_active:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'No active game to end - status: (`{self.game_tbl.status.name}`)')
        self.end_round()
        self.game_tbl.end_time = datetime.utcnow()
        self.game_tbl.status = GameStatuses.ended

    def get_next_judge(self):
        """Gets the following judge by the order set"""
        self.prev_judge = self.judge
        cur_judge_pos = self.players.get_player_index(self.judge.player_id)
        self.players.player_list[cur_judge_pos].player_round_table.is_judge = False
        next_judge_pos = 0 if cur_judge_pos == len(self.players.player_list) - 1 else cur_judge_pos + 1
        self.judge = self.players.player_list[next_judge_pos]
        self.judge.pick_idx = None
        self.players.player_list[next_judge_pos].player_round_table.is_judge = True

    def _deal_card(self):
        if len(self.deck.answers_card_list) == 0:
            raise ValueError('No more cards left to deal!')
        return self.deck.deal_answer_card()

    def deal_cards(self, num_cards: int):
        """Deals cards out to players by indicating the number of cards to give out"""
        for player in self.players.player_list:
            if self.game_tbl.rounds > 1 and self.judge.player_id == player.player_id:
                # Skip judge if dealing after first round
                continue
            card_list = [self._deal_card() for i in range(num_cards)]
            self.players.take_dealt_cards(player, card_list=card_list)

    def decknuke(self, player_id: str):
        player = self.players.get_player(player_attr=player_id, attr_name='player_id')
        if self.judge.player_id == player.player_id:
            self.st.message_test_channel(f'Decknuke rejected. {player.player_tag} is the judge. :shame:')
            return
        # Randpick a card for this user
        self.process_picks(player_id, 'randpick')
        # Remove all cards form their hand & tag player
        self.players.process_player_decknuke(player)
        self.st.message_test_channel(f'{player.player_tag} nuked their deck! :frogsiren:')
        # Deal the player the unused new cards the number of cards played will be replaced after the round ends.
        n_cards = DECK_SIZE - self.current_question_card.required_answers
        card_list = [self._deal_card() for i in range(n_cards)]
        self.players.take_dealt_cards(player, card_list=card_list)

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
        success = player.hand.pick_card(picks)
        if success:
            # Replace the pick messages
            self.replace_block_forms(player)
            return f'*`{player.display_name}`*\'s pick has been registered.'
        elif not success and not player.hand.pick.is_empty():
            return f'*`{player.display_name}`*\'s pick voided. You already picked.'
        else:
            return 'Pick not registered.'

    def players_left_to_pick(self) -> List[str]:
        """Returns a list of the players that have yet to pick a card"""
        remaining = []
        for player in self.players.player_list:
            if player.hand.pick.is_empty() and player.player_id != self.judge.player_id:
                remaining.append(player.display_name)
        return remaining

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self.game_settings_tbl.ping_judge = not self.game_settings_tbl.ping_judge

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        self.game_settings_tbl.ping_winner = not self.game_settings_tbl.ping_winner

    def process_picks(self, user: str, message: str) -> Optional:
        """Processes the card selection made by the user"""

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

        if player.player_table.is_dm_cards and 'randpick' in message:
            # Ping player their randomly selected picks if they've chosen to be DMed cards
            self.st.private_message(player.player_id, f'Your randomly selected pick(s): '
                                                      f'{player.hand.pick.render_pick_list_as_str()}')

        # See who else has yet to decide
        remaining = self.players_left_to_pick()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.game_settings_tbl.is_ping_judge:
                judge_msg = f'{self.judge.player_tag} to judge.'
            else:
                judge_msg = f'`{self.judge.display_name.title()}` to judge.'
            messages.append(judge_msg)
            self.game_tbl.status = GameStatuses.judge_decision
            # Update the "remaining picks" message
            self.st.update_message(auto_config.MAIN_CHANNEL, self.round_ts, message='lol')
            self._display_picks(notifications=messages)
            # Handle auto randchoose players
            for player in self.players.player_list:
                if player.auto_randchoose:
                    if player.player_id == self.judge.player_id:
                        # Judge only
                        self.choose_card(player.player_id, 'randchoose')
        else:
            # Make the remaining players more visible
            remaining_txt = ' '.join([f'`{x}`' for x in remaining])
            messages.append(f'*`{len(remaining)}`* players remaining to decide: {remaining_txt}')
            msg_block = [bkb.make_context_section(messages)]
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
                bkb.make_context_section(notifications),
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
        if self.judge.player_table.is_dm_cards:
            # DM choices to player if they have card dming enabled
            dm_chan, ts = self.st.private_message(self.judge.player_id, message='', ret_ts=True,
                                                  blocks=judge_response_block)

    def display_picks(self) -> Tuple[List[dict], List[dict]]:
        """Shows the player's picks in random order"""

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
        honorifics = [
            'lackey', 'intern', 'young padawan', 'master apprentice', 'honorable', 'respected and just',
            'cold and yet still fair', 'worthy inheriter of daddy\'s millions', 'mother of dragons', 'excellent',
            'elder', 'ruler of the lower cards', 'most fair dictator of difficult choices',
            'benevolent and omniscient chief of dutiful diddling', 'supreme high chancellor of card justice'
        ]
        judge_pts = self.session.query(func.sum(TablePlayerRounds)).filter(and_(
            TablePlayerRounds.player_id == self.judge.player_id,
            TablePlayerRounds.game_id == self.game_tbl.id
        )).scalar()
        honorific = f'the {honorifics[-1] if judge_pts > len(honorifics) - 1 else honorifics[judge_pts]}'
        # Assign this to the judge so we can refer to it in other areas.
        self.judge.player_table.honorific = honorific.title()
        self.session.commit()
        bot_moji = ':math:' if self.judge.player_table.is_auto_randchoose else ''

        return [
            bkb.make_block_section(
                f'Round *`{self.game_tbl.rounds}`* - *{self.judge.player_table.honorific} '
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
                return None
        else:
            pick = self._get_pick(user, message, judge_decide=True)

        if pick > len(self.players.player_list) - 2 or pick < 0:
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
                    self.judge.pick_idx = pick
                else:
                    self.st.message_test_channel('Judge\'s pick voided. You\'ve already picked this round.')

    def _randchoose_handling(self, message: str) -> Optional[Tuple[int, bool]]:
        """Contains all the logic for handling a randchoose command"""
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
