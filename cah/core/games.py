#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime
from random import (
    choice,
    shuffle,
)
import re
import time
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Tuple,
)

from loguru import logger
import numpy as np
from slack_sdk.errors import SlackApiError
from slacktools import SlackBotBase
from slacktools.block_kit.base import BlocksType
from slacktools.block_kit.blocks import (
    ButtonSectionBlock,
    DividerBlock,
    MarkdownContextBlock,
    MarkdownSectionBlock,
    MultiStaticSelectSectionBlock,
)
from sqlalchemy.sql import and_

from cah.core.players import (
    Judge,
    Player,
    Players,
)
from cah.core.selections import (
    Choice,
    Pick,
)
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    GameStatus,
    RipType,
    SettingType,
    TableAnswerCard,
    TableGame,
    TableGameRound,
    TablePlayer,
    TablePlayerRound,
    TableQuestionCard,
)
from cah.queries.game_queries import (
    GameQueries,
    PickItemType,
)

if TYPE_CHECKING:
    from cah.core.deck import Deck


# Define statuses where game is not active
GAME_NOT_ACTIVE = [GameStatus.INITIATED, GameStatus.ENDED]
# Status when ready to transition into new round
NEW_ROUND_READY = [GameStatus.INITIATED, GameStatus.END_ROUND]

DECK_SIZE = 5


class OutOfCardsException(Exception):
    pass


class Game:
    """Holds data for current game"""

    def __init__(self, player_hashes: List[str], deck: 'Deck', st: SlackBotBase, eng: WizzyPSQLClient,
                 parent_log: logger, config, game_id: int = None):
        self.st = st
        self.eng = eng
        self.config = config
        self.judge_order_divider = self.eng.get_setting(SettingType.JUDGE_ORDER_DIVIDER)
        self.log = parent_log.bind(child_name=self.__class__.__name__)
        self.gq = GameQueries(eng=eng, log=self.log)
        self.log.debug(f'Building out new game with deck as combo: {deck.deck_combo}...')

        # Database table links
        self.is_existing_game = game_id is not None
        if self.is_existing_game:
            self.game_id = game_id
            self.log.debug(f'A preexisting game id was provided ({game_id}). Building a game from that.')
            with self.eng.session_mgr() as session:
                self.game_tbl = session.query(TableGame).filter(TableGame.game_id == game_id).one_or_none()
                self.status = self.game_tbl.status
                self.game_round_tbl = session.query(TableGameRound).filter(and_(
                    TableGameRound.game_key == self.game_tbl.game_id,
                )).order_by(TableGameRound.game_round_id.desc()).limit(1).one_or_none()
                self.game_round_id = self.game_round_tbl.game_round_id
                session.expunge_all()
        else:
            self.log.debug('Starting a new game...')
            # Create a new game
            self._status = GameStatus.INITIATED
            game_tbl = TableGame(deck_combo=deck.deck_combo, status=self._status)
            # Add the object to the database & refresh to get ids
            self.game_tbl = self.eng.refresh_table_object(game_tbl)  # type: TableGame
            # These ones will be set when new_round() is called
            self.game_round_tbl = None  # type: Optional[TableGameRound]
            self.game_round_id = None  # type: Optional[int]
            self.game_id = self.game_tbl.game_id

        # Load settings
        self._is_ping_judge = self.eng.get_setting(SettingType.IS_PING_JUDGE)
        self._is_ping_winner = self.eng.get_setting(SettingType.IS_PING_WINNER)
        self._decknuke_penalty = self.eng.get_setting(SettingType.DECKNUKE_PENALTY)
        # Load players
        self.log.debug(f'Setting {len(player_hashes)} players as active for this game.')
        self.eng.set_active_players(player_hashes)
        self.players = Players(
            player_hash_list=player_hashes, slack_api=self.st, eng=self.eng, parent_log=self.log,
            config=self.config, is_existing=self.is_existing_game
        )  # type: Players
        if self.is_existing_game:
            # Get the current round's judge
            with self.eng.session_mgr() as session:
                _judge: TablePlayer
                _judge = session.query(TablePlayer).\
                    join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).\
                    filter(and_(
                        TablePlayerRound.game_round_key == self.game_round_id,
                        TablePlayerRound.is_judge
                    )).one_or_none()
                if _judge is None:
                    self.log.warning('Judge wasn\'t found. Selecting at random.')
                _judge_hash = _judge.slack_user_hash
        else:
            _judge_hash = self.players.judge_order[0]
        self.judge = Judge(player_hash=_judge_hash, eng=self.eng, log=self.log)      # type: Judge
        self.prev_judge = None          # type: Optional[Judge]
        self.game_start_time = self.game_tbl.start_time

        self.deck = deck

        self.current_question_card = None  # type: Optional[TableQuestionCard]
        self.deck.shuffle_deck()

    @property
    def status(self) -> GameStatus:
        return self._status

    @status.setter
    def status(self, value: GameStatus):
        self._status = value
        with self.eng.session_mgr() as session:
            session.query(TableGame).filter(TableGame.game_id == self.game_id).update({
                'status': self._status
            })

    @property
    def is_ping_judge(self) -> bool:
        return self._is_ping_judge

    @is_ping_judge.setter
    def is_ping_judge(self, value: bool):
        self._is_ping_judge = value
        self.eng.set_setting(SettingType.IS_PING_JUDGE, self._is_ping_judge)

    @property
    def decknuke_penalty(self) -> int:
        return self._decknuke_penalty

    @decknuke_penalty.setter
    def decknuke_penalty(self, value: int):
        self._decknuke_penalty = value
        self.eng.set_setting(SettingType.DECKNUKE_PENALTY, self._decknuke_penalty)

    @property
    def is_ping_winner(self) -> bool:
        return self._is_ping_winner

    @is_ping_winner.setter
    def is_ping_winner(self, value: bool):
        self._is_ping_winner = value
        self.eng.set_setting(SettingType.IS_PING_WINNER, self._is_ping_winner)

    @property
    def game_round_number(self) -> int:
        """Retrieves the round number from the db"""
        with self.eng.session_mgr() as session:
            tbl = session.query(TableGame).filter(TableGame.game_id == self.game_id).one_or_none()
            if tbl is None:
                return 0
            return len(tbl.rounds)

    def get_judge_order(self) -> str:
        """Determines order of judges """
        return f' {self.judge_order_divider} '.join([f'`{self.players.player_dict[x].display_name}`'
                                                     for x in self.players.judge_order])

    def reinstate_round(self):
        """Reinstates an existing round after a reboot"""
        with self.eng.session_mgr() as session:
            self.current_question_card = session.query(TableQuestionCard). \
                join(TableGameRound, TableGameRound.question_card_key == TableQuestionCard.question_card_id). \
                filter(and_(
                    TableGameRound.game_round_id == self.game_round_id
                )).one_or_none()
            session.expunge(self.current_question_card)
        self.log.debug('Existing game loading process is now complete. '
                       'Setting the existing game toggle to False.')
        self.is_existing_game = False

        self.players.reinstate_round_players(game_id=self.game_id, game_round_id=self.game_round_id)

        round_number = self.game_round_number
        self.log.debug(f'Game round {round_number} continues...')

    def new_round(self, notification_block: List[Dict] = None) -> Optional[BlocksType]:
        """Starts a new round"""
        self.log.debug('Working on new round...')
        if self.status not in NEW_ROUND_READY:
            self.log.error(f'Status wasn\'t right for a new round: {self.status.name}')
            # Avoid starting a new round when one has already been started
            raise ValueError(f'Cannot transition to new round due to current status '
                             f'(`{self.status.name}`)')

        if self.game_round_number > 0:
            self.log.debug('Ending previous round first...')
            # Not the first round...
            self.end_round()

        # Determine if the game should be ended before proceeding
        if len(self.deck.questions_card_list) == 0:
            self.log.debug('No more questions available. Ending game')
            # No more questions, game hath ended
            self.end_game()
            return [
                MarkdownSectionBlock(f'No more question cards! Game over! {":party-dead:" * 3}')
            ]

        # Scan names in the db vs. in the player object to ensure they're the same
        self.log.debug('Confirming display name parity...')
        for uid, player in self.players.player_dict.items():
            tbl_display_name = player.pq.get_player_table(player_hash=uid).display_name
            if player.display_name != tbl_display_name:
                self.log.debug(f'Changing {player.display_name} to {tbl_display_name}')
                # Set player display name to the name found in the database
                self.players.player_dict[uid].display_name = tbl_display_name

        if notification_block is None:
            notification_block = []

        self.game_round_tbl = TableGameRound(game_key=self.game_id)

        # Determine number of cards to deal to each player & deal
        # either full deck or replacement cards for previous question
        # Deal question card
        self.current_question_card = self.deck.deal_question_card()
        self.game_round_tbl.question_card_key = self.current_question_card.question_card_id
        # Send new round to db, pull that data back in to capture id
        self.game_round_tbl = self.eng.refresh_table_object(self.game_round_tbl)

        self.game_round_id = self.game_round_tbl.game_round_id

        round_number = self.game_round_number

        lines = '=' * 32
        self.log.debug(f'\n{lines}\n\t\tROUND {round_number} STARTED ({self.game_round_id})\n{lines}')

        # Prep player list for new round
        self.players.new_round(game_id=self.game_id, game_round_id=self.game_round_id)

        # Get new judge if not the first round. Mark judge as such in the db
        self.get_next_judge(n_round=round_number, game_id=self.game_id, game_round_id=self.game_round_id)

        self.deal_cards()
        self.status = GameStatus.PLAYER_DECISION

        self.st.private_channel_message(self.judge.player_hash, self.config.MAIN_CHANNEL,
                                        ":gavel::gavel::gavel: You're the judge this round! :gavel::gavel::gavel:")
        question_block = self.make_question_block()
        notification_block += question_block
        self.log.debug('Sending question block to channel...')
        self.st.message_main_channel(blocks=notification_block)

        # Next, send a message to the channel about players to pick...
        self.log.debug('Sending pick reception block to channel...')
        remaining = self.players_left_to_pick()
        # Make the remaining players more visible
        self.log.debug(f'{len(remaining)} remaining to decide.')
        remaining_txt = ' '.join([f'`{x}`' for x in remaining])
        messages = [f'*`{len(remaining)}`* players remaining to decide: {remaining_txt}']
        msg_block = [MarkdownContextBlock(messages)]
        round_msg_ts = self.st.send_message(self.config.MAIN_CHANNEL,
                                            message='A new round hath begun',
                                            ret_ts=True, blocks=msg_block)
        self.game_round_tbl.message_timestamp = round_msg_ts
        self.game_round_tbl = self.eng.refresh_table_object(self.game_round_tbl)

        self.log.debug('Wiping all data for choice_order')
        with self.eng.session_mgr() as session:
            session.query(TablePlayer).update({
                TablePlayer.choice_order: None
            })

        # Last, render hands for the players
        self.log.debug('Waiting 5 seconds before rendering the players\' hands...')
        time.sleep(5)
        self.log.debug('Rendering player hands and sending them')
        self.handle_render_hands()
        self.handle_autorandpicks()

    def end_round(self):
        """Procedures for ending the round"""
        self.log.debug('Ending round.')
        # Update the previous round with an end time
        with self.eng.session_mgr() as session:
            session.query(TableGameRound).filter(TableGameRound.game_round_id == self.game_round_id).update({
                TableGameRound.end_time: datetime.now()
            })
        self.status = GameStatus.END_ROUND

    def end_game(self):
        """Ends the game"""
        self.log.debug('End game process started')
        if self.status is GAME_NOT_ACTIVE:
            # Avoid starting a new round when one has already been started
            raise ValueError(f'No active game to end - status: (`{self.status.name}`)')
        self.end_round()
        self.log.debug('Wiping cards from players\' hands...')
        self.players.reset_player_hands()

        with self.eng.session_mgr() as session:
            session.query(TableGame).filter(TableGame.game_id == self.game_id).update({
                TableGame.end_time: datetime.now()
            })
        self.status = GameStatus.ENDED

    def handle_render_hands(self):
        # Get the required number of answers for the current question
        self.log.debug('Rendering hands process beginning.')
        req_ans = self.current_question_card.responses_required
        question_block = self.make_question_block()
        try:
            self.players.render_hands(judge_hash=self.judge.player_hash, question_block=question_block,
                                      req_ans=req_ans)
        except OutOfCardsException:
            self.log.debug('Stopping game - ran out of cards!')
            blocks = [
                MarkdownSectionBlock(f'The people have run out of answer cards! Game over! {":party-dead:" * 3}')
            ]
            self.st.message_main_channel(blocks=blocks)
            self.end_game()
            return None

    def handle_autorandpicks(self):
        """Handles autorandpicking for players that have had it turned on"""
        # Determine randpick players and pick for them
        self.log.debug('Handling randpicks for round')
        for player_hash, player in self.players.player_dict.items():
            if player_hash == self.judge.player_hash:
                continue
            elif player.is_arp:
                # Player has elected to automatically pick their cards
                rand_roll = np.random.random()
                if rand_roll <= 0.10:
                    self.decknuke(player_hash=player_hash)
                else:
                    self.process_picks(player_hash, 'randpick')
                if player.is_dm_cards:
                    self.st.private_message(player_hash, 'Your pick was handled automatically, '
                                                         'as you have `auto randpick` (ARP) enabled.')

    def determine_honorific(self):
        """Determines the honorific for the judge"""
        # Determine honorific for judge
        self.log.debug('Determining honorific for judge...')
        # Assign this to the judge so we can refer to it in other areas.
        self.judge.get_honorific()

    def get_next_judge(self, n_round: int, game_id: int, game_round_id: int):
        """Gets the following judge by the order set"""
        self.log.debug('Determining judge.')
        if n_round > 1:
            # Rotate judge
            self.prev_judge = self.judge
            if self.players.player_dict.get(self.prev_judge.player_hash) is not None:
                self.players.player_dict[self.prev_judge.player_hash].is_judge = False
                prev_judge_pos = self.players.judge_order.index(self.prev_judge.player_hash)
                next_judge_pos = 0 if prev_judge_pos == len(self.players.player_dict) - 1 else prev_judge_pos + 1
                _judge = self.players.judge_order[next_judge_pos]
            else:
                # Just select the judge at random from the list
                _judge = choice(self.players.judge_order)
            self.judge = Judge(player_hash=_judge, eng=self.eng, log=self.log)
        self.judge.game_id = game_id
        self.judge.game_round_id = game_round_id
        self.judge.is_judge = True
        # Regenerate the honorific for the new judge
        self.determine_honorific()

    def _deal_card(self) -> Optional[TableAnswerCard]:
        if len(self.deck.answers_card_list) == 0:
            self.log.debug('No more cards left to deal!!!!!')
            return None
        return self.deck.deal_answer_card()

    def deal_cards(self):
        """Deals cards out to players by indicating the number of cards to give out"""
        for p_hash, p_obj in self.players.player_dict.items():
            if self.deck.num_answer_cards == 0:
                break
            if self.game_round_number > 1 and self.judge.player_hash == p_hash:
                # Skip judge if dealing after first round
                continue
            if p_obj.get_nonreplaceable_cards() == DECK_SIZE:
                continue
            num_cards = DECK_SIZE - p_obj.get_nonreplaceable_cards()
            if num_cards > 0:
                self.log.debug(f'Dealing {num_cards} cards to {p_obj.display_name}')
                card_list = [self._deal_card() for _ in range(num_cards)]
                self.players.take_dealt_cards(player_hash=p_hash, card_list=card_list)
                self.log.debug(f'Player {p_obj.display_name} now has {p_obj.get_all_cards()} cards')
            else:
                self.log.warning(f'Player {p_obj.display_name} now has {p_obj.get_all_cards()} cards')

    def decknuke(self, player_hash: str):
        player = self.players.player_dict[player_hash]
        self.log.debug(f'Player {player.display_name} has nuked their deck. Processing command.')
        if self.judge.player_hash == player_hash:
            self.st.message_main_channel(f'Decknuke rejected. {player.player_tag} you is the judge baby. :shame:')
            return
        # Randpick a card for this user
        if player.get_all_cards() < self.current_question_card.responses_required:
            self.st.message_main_channel(f'Decknuke rejected. {player.player_tag} you haz ranned '
                                         f'out of cahds. :shame:')
            self.end_game()
            return
        self.process_picks(player_hash, 'randpick')
        # Remove all cards form their hand & tag player
        self.players.process_player_decknuke(player_hash=player_hash)
        addl_txt = '...also, we\'re out of cards hehe..' if self.deck.num_answer_cards == 0 else ''
        self.st.message_main_channel(f'{player.player_tag} nuked their deck! :frogsiren: {addl_txt}')
        # Deal the player the unused new cards the number of cards played will be replaced after the round ends.
        n_cards = DECK_SIZE - self.current_question_card.responses_required
        card_list = [self._deal_card() for _ in range(n_cards)]
        self.players.take_dealt_cards(player_hash=player_hash, card_list=card_list)

    def round_wrap_up(self):
        """Coordinates end-of-round logic (tallying votes, picking winner, etc.)"""
        # Make sure all users have votes and judge has made decision before wrapping up the round
        # Handle the announcement of winner and distribution of points
        self.st.message_main_channel(blocks=self.winner_selection())
        self.status = GameStatus.END_ROUND
        self.log.debug('Waiting 5 seconds before rendering the next round\'s hands...')
        time.sleep(5)
        # Start new round
        self.new_round()

    def winner_selection(self) -> BlocksType:
        """Contains the logic that determines point distributions upon selection of a winner"""
        # Get the list of cards picked by each player
        self.log.debug(f'Selecting winner at index: {self.judge.selected_choice_idx} ({self.judge.winner_hash})')

        # Winner selection
        winner = self.players.player_dict.get(self.judge.winner_hash)
        winner_was_none = winner is None  # This is used later in the method
        if winner_was_none:
            # Likely the player who won left the game. Add to their overall points
            self.log.debug('The winner selected seems to have left the game. Spinning their object up to '
                           'grant their points.')
            # Load the Player object so we can make the same changes as an existing player
            winner = Player(player_hash=self.judge.winner_hash, eng=self.eng, log=self.log)
            # Attach the current round to the winner
            winner.game_id = self.game_id
            winner.round_id = self.game_round_id

        self.log.debug(f'Winner selected as "{winner.display_name}"')
        # If decknuke occurred, distribute the points to others randomly
        if winner.is_nuked_hand:
            penalty = self.decknuke_penalty
            point_receivers_txt = self._points_redistributer(penalty)
            points_won = penalty
            impact_rpt = ':impact:' * 4
            decknuke_txt = f'\n{impact_rpt}{self.gq.get_rip(rip_type=RipType.DECKNUKE)}\n' \
                           f'You got got and your points were redistributed such: {point_receivers_txt}'
            winner.is_nuked_hand_caught = True
        else:
            points_won = 1
            decknuke_txt = ''

        # Mark card as chosen in db
        self.log.debug('Marking chosen card(s) in db.')
        winner.mark_chosen_pick()

        winner.add_points(points_won)
        if not winner_was_none:
            self.players.player_dict[winner.player_hash] = winner
        winner_details = winner.player_tag if self.is_ping_winner else f'*`{winner.display_name.title()}`*'

        # Take question card, replace `_` with the answers
        sentence_with_winner = self.winning_answer_placement(
            question=self.current_question_card.card_text,
            answers=winner.render_picks_as_list()
        )

        last_section = [
            DividerBlock(),
            MarkdownContextBlock(f'Round ended. Nice going, {self.judge.display_name}.')
        ]

        message_block = [
            MarkdownContextBlock(':tada: And the winner is...'),
            MarkdownSectionBlock(f"*{sentence_with_winner}*"),
            MarkdownContextBlock([
                f"*`{points_won:+}`* :diddlecoin: to {winner_details}! ",
                f"New score: *`{winner.get_current_score()}`* :diddlecoin: "
            ]),
        ]
        if decknuke_txt != '':
            message_block.append(MarkdownSectionBlock(decknuke_txt))
        return message_block + last_section

    @staticmethod
    def winning_answer_placement(question: str, answers: List[str]) -> str:
        winning_sentence = ''
        last_pos = 0
        for i, mtch in enumerate(re.finditer('[_]+', question)):

            winning_sentence += question[last_pos:mtch.regs[0][0]]
            try:
                answer = answers.pop(0)
            except IndexError:
                answer = '<missing-answer--gasp>'
            winning_sentence += f'`{answer}`'
            last_pos = mtch.regs[0][1]
        if last_pos < len(question) - 1:
            winning_sentence += question[last_pos:]
        if len(answers) > 0:
            winning_sentence += ','.join((f' `{x}`' for x in answers))
        return winning_sentence.replace('*', '✱')

    def _points_redistributer(self, penalty: int) -> str:
        """Handles the logic covering redistribution of wealth among players"""
        self.log.debug('Redistributing points post discovered decknuke')
        # Deduct points from the judge, give randomly to others
        point_receivers = {}  # Store 'name' (of player) and 'points' (distributed)
        # Determine the eligible receivers of the extra points
        nonjudge_players = [v for k, v in self.players.player_dict.items()
                            if v.player_hash != self.judge.player_hash]
        player_points_list = [x.get_current_score() for x in nonjudge_players]
        eligible_receivers = [x for x in nonjudge_players]
        # Some people have earned points already. Make sure those with the highest points aren't eligible
        max_points = max(player_points_list)
        min_points = min(player_points_list)
        if max_points - min_points > 3:
            eligible_receivers = [x for x in nonjudge_players if x.get_current_score() < max_points]
        for pt in range(0, penalty * -1):
            player: Player
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
            if player.player_hash in point_receivers.keys():
                # Add another point
                point_receivers[player.player_hash]['points'] += 1
            else:
                point_receivers[player.player_hash] = {
                    'name': player.display_name,
                    'points': 1
                }
            self.players.player_dict[player.player_hash] = player
        point_receivers_txt = '\n'.join([f'`{v["name"]}`: *`{v["points"]}`* :diddlecoin:'
                                         for k, v in point_receivers.items()])
        return point_receivers_txt

    def replace_block_forms(self, player_hash: str):
        """Replaces the Block UI form with another message"""
        player = self.players.player_dict[player_hash]
        blk = [
            MarkdownSectionBlock(f'Your pick(s): {player.render_picks_as_str()}')
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
        self.players.reset_player_pick_block(player_hash=player_hash)

    def assign_player_pick(self, player_hash: str, picks: List[int]) -> str:
        """Takes in an int and assigns it to the player who wrote it"""
        player = self.players.player_dict[player_hash]
        self.log.debug(f'Received pick request from player {player.display_name}: {picks}')
        success = player.pick_card(picks)
        if success:
            # Replace the pick messages
            self.log.debug('Pick assignment successful. Updating player.')
            player.is_picked = True
            self.players.player_dict[player_hash] = player
            self.replace_block_forms(player_hash)
            return f'*`{player.display_name}`*\'s pick has been registered.'
        elif not success and player.is_picked:
            self.log.debug('Pick assignment unsuccessful. Player likely already picked.')
            return f'*`{player.display_name}`*\'s pick voided. You already picked.'
        else:
            self.log.debug('Pick assignment unsuccessful. Other reason.')
            return 'Pick not registered.'

    def players_left_to_pick(self, as_name: bool = True) -> List[str]:
        """Returns a list of the players that have yet to pick a card"""
        self.log.debug('Determining players remaining to pick')
        remaining = []
        for p_hash, p_obj in self.players.player_dict.items():
            if not p_obj.is_picked and p_hash != self.judge.player_hash:
                if as_name:
                    remaining.append(p_obj.display_name)
                else:
                    remaining.append(p_hash)
        return remaining

    def toggle_judge_ping(self):
        """Toggles whether or not to ping the judge when all card decisions have been completed"""
        self.log.debug('Toggling judge pinging')
        self.is_ping_judge = not self.is_ping_judge

    def toggle_winner_ping(self):
        """Toggles whether or not to ping the winner when they've won a round"""
        self.log.debug('Toggling winner pinging')
        self.is_ping_winner = not self.is_ping_winner

    def process_picks(self, player_hash: str, message: str) -> Optional:
        """Processes the card selection made by the user"""
        # Try to load details from the pick message
        # Get the player
        self.log.debug(f'Processing pick from {player_hash}.')
        player = self.players.player_dict[player_hash]
        self.log.debug(f'...({player.display_name})...')
        # Handle processing the pick from the message
        pick = Pick(player_hash=player_hash, message=message,
                    n_required=self.current_question_card.responses_required, total_cards=player.get_all_cards())

        if pick.player_hash == self.judge.player_hash:
            # Make sure the player referenced isn't the judge
            self.log.debug('Ignoring pick... This player is the judge.')
            self.st.message_main_channel(f'{self.judge.player_tag} is the judge this round. Judges can\'t pick!!!')
            return None
        elif player_hash != pick.player_hash:
            # Reload player - a pick was called in for someone other than the command sender
            self.log.debug('Replacing player variable, as pick was called in for another player')
            player = self.players.player_dict[pick.player_hash]

        if player.is_picked:
            # Player already picked
            self.log.debug('Ignoring pick... Player has already picked.')
            self.st.message_main_channel(f'{player.player_tag} you already pickled this round????? NO DOUBLE PICKLE!!!')
            return None
        pick.handle_pick(total_cards=player.get_all_cards())

        if pick.picks is None:
            self.log.debug('Picks object was still NoneType at this point.')
            if pick.n_required != len(pick.positions):
                self.st.message_main_channel(f'Dearest <@{player_hash}>, you picked {len(pick.positions)} things, but '
                                             f'the question needs {pick.n_required}.')
            return None
        elif any([x > player.get_all_cards() - 1 or x < 0 for x in pick.picks]):
            self.st.message_main_channel(f'<@{player_hash}> I think you picked outside the range of suggestions. '
                                         f'Your picks: `{pick.picks}`.')
            return None
        messages = [self.assign_player_pick(player.player_hash, pick.picks)]

        if player.is_dm_cards and 'randpick' in message:
            # Ping player their randomly selected picks if they've chosen to be DMed cards
            self.st.private_message(player.player_hash, f'Your randomly selected pick(s): '
                                                        f'{player.render_picks_as_str()}')

        # See who else has yet to decide
        remaining = self.players_left_to_pick()
        if len(remaining) == 0:
            messages.append('All players have made their picks.')
            if self.is_ping_judge:
                judge_msg = f'{self.judge.player_tag} to judge.'
            else:
                judge_msg = f'`{self.judge.display_name.title()}` to judge.'
            messages.append(judge_msg)
            self.status = GameStatus.JUDGE_DECISION
            # Update the "remaining picks" message
            self.st.update_message(self.config.MAIN_CHANNEL, self.game_round_tbl.message_timestamp,
                                   message='Pickling complete!')
            self._display_picks(notifications=messages)
            # Handle auto randchoose players
            self.log.debug(f'All players made their picks. Checking if judge is arc: {self.judge.is_arc}')
            if self.judge.is_arc:
                self.choose_card(player_hash=self.judge.player_hash, message='randchoose')
                if self.judge.selected_choice_idx is not None:
                    self.round_wrap_up()
        else:
            # Make the remaining players more visible
            self.log.debug(f'{len(remaining)} remaining to decide.')
            remaining_txt = ' '.join([f'`{x}`' for x in remaining])
            messages.append(f'*`{len(remaining)}`* players remaining to decide: {remaining_txt}')
            msg_block = [MarkdownContextBlock(messages)]
            if self.game_round_tbl.message_timestamp is None:
                # Announcing the picks for the first time; capture the timestamp so
                #   we can update that same message later
                round_msg_ts = self.st.send_message(self.config.MAIN_CHANNEL,
                                                    message='Message about current game!',
                                                    ret_ts=True, blocks=msg_block)
                self.game_round_tbl.message_timestamp = round_msg_ts
                self.game_round_tbl = self.eng.refresh_table_object(self.game_round_tbl)
            else:
                # Update the message we've already got
                self.st.update_message(self.config.MAIN_CHANNEL, self.game_round_tbl.message_timestamp,
                                       blocks=msg_block)

    def _display_picks(self, notifications: List[str] = None):
        """Shows a random order of the picks"""
        if notifications is not None:
            public_response_block = [
                MarkdownContextBlock(notifications),
                DividerBlock()
            ]
        else:
            public_response_block = []
        question_block = self.make_question_block()
        public_choices, private_choices = self.display_picks()
        public_response_block += question_block + public_choices
        # Judge's block
        judge_response_block = question_block + private_choices
        # Show everyone's picks to the group, but only send the choice buttons to the judge
        self.st.message_main_channel(blocks=public_response_block)

        # Handle sending judge messages
        # send as private in-channel message (though this sometimes goes unrendered)
        _ = self.st.private_channel_message(self.judge.player_hash, self.config.MAIN_CHANNEL,
                                            message='', ret_ts=True, blocks=judge_response_block)
        if self.judge.is_dm_cards:
            # DM choices to player if they have card dming enabled
            _, _ = self.st.private_message(self.judge.player_hash, message='', ret_ts=True,
                                           blocks=judge_response_block)

    def display_picks(self) -> Tuple[BlocksType, BlocksType]:
        """Shows the player's picks in random order"""
        self.log.debug('Rendering picks...')
        picks: Dict[str, List[PickItemType]]
        picks = self.gq.get_player_picks(game_round_id=self.game_round_id)
        player_hashes = list(picks.keys())
        shuffle(player_hashes)

        judge_card_blocks = []
        public_card_blocks = []
        randbtn_list = []  # Just like above, but bear a 'rand' prefix to differentiate. These can be subset.
        for i, p_hash in enumerate(player_hashes):
            # Load choice order in player table
            self.players.player_dict[p_hash].choice_order = i
            num = i + 1
            pick = picks.get(p_hash)
            pick_txt_list = [x.get('card_text') for x in pick]
            single_option_txt = "|".join([f" *`{x[:75]}`* " for x in pick_txt_list])
            option_btn_txt = "|".join([f" {x[:30]} " for x in pick_txt_list])
            # Make a block specifically for the judge (with buttons)
            pick_txt = f'*{num}*: {single_option_txt}'
            judge_card_blocks.append(
                ButtonSectionBlock(pick_txt, f'{num}', value=f'choose-{num}', action_id=f'game-choose-{num}')
            )
            # Make a "public" block that just shows the choices in the channel
            public_card_blocks.append(MarkdownSectionBlock(pick_txt))
            randbtn_list.append((f'{option_btn_txt}', f'randchoose-{num}'))

        rand_options = [(':hyper-shrug: All choices', 'randchoose-all')] + randbtn_list

        return public_card_blocks, judge_card_blocks + [
            DividerBlock(),
            MultiStaticSelectSectionBlock('Randchoose (all or subset)', placeholder='Selectionize!',
                                          option_pairs=rand_options, action_id='game-randchoose'),
            ButtonSectionBlock('Force Close', 'Close', value='none', action_id='close')
        ]

    def make_question_block(self, hide_arc: bool = False) -> BlocksType:
        """Generates the question block for the current round"""
        bot_moji = ':math:' if self.judge.is_arc and not hide_arc else ''

        return [
            MarkdownSectionBlock(
                f'Round *`{self.game_round_number}`* - *{self.judge.honorific} '
                f'Judge {self.judge.display_name.title()}* {bot_moji} presiding.'
            ),
            MarkdownSectionBlock(f'*:regional_indicator_q:: `{self.current_question_card.card_text}`*'),
            DividerBlock(),
        ]

    def choose_card(self, player_hash: str, message: str) -> Optional:
        """For the judge to choose the winning card and
        for other players to vote on the card they think should win"""

        if player_hash in self.config.ADMINS and 'blueberry pie' in message:
            # Overrides the block below to allow admin to make a choice during testing or special circumstances
            self.log.info('Process overridden w/ admin command to randchoose for judge.')
            player_hash = self.judge.player_hash
            message = 'randchoose'

        if player_hash != self.judge.player_hash:
            self.log.debug(f'Nonjudge user tried to choose: {player_hash}')
            self.st.message_main_channel(f'<@{player_hash}>, you\'re not the judge!')
            return None

        max_position = len(self.players.player_dict) - 2
        chce = Choice(player_hash=player_hash, message=message, max_position=max_position)

        if chce.choice > max_position or chce.choice < 0:
            self.log.debug(f'Choice ({chce.choice}) was outside of spec.')
            # Pick is rendered as an array index here.
            # Pick can either be:
            #   -less than total players minus judge, minus 1 more to account for array
            #   -greater than -1
            self.st.message_main_channel(f'I think you picked outside the range of suggestions. '
                                         f'Your choice: {chce.choice}')
            return None
        else:
            # Record the judge's pick
            if self.judge.selected_choice_idx is None:
                self.log.debug(f'Setting judge\'s choice as {chce.choice}:')
                self.judge.selected_choice_idx = chce.choice
                self.judge.get_winner_from_choice_order()
            else:
                self.st.message_main_channel('Judge\'s pick voided. You\'ve already picked this round.')
