#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import (
    List,
    Optional,
    Union,
    Dict
)
from random import shuffle
from sqlalchemy.sql import (
    func,
    and_
)
from easylogger import Log
from slacktools import SlackTools
import cah.app as cah_app
from cah.model import (
    TableHonorific,
    TablePlayer,
    TablePlayerRound
)
from cah.db_eng import WizzyPSQLClient
from cah.settings import auto_config
from cah.core.cards import (
    AnswerCard,
    Hand
)
from cah.core.common_methods import refresh_players_in_channel


class Player:
    """Player-specific things"""

    def __init__(self, player_hash: str, eng: WizzyPSQLClient, log: Log):
        self.player_hash = player_hash
        self.player_tag = f'<@{self.player_hash}>'
        self.log = log
        self.eng = eng

        player_table = self._get_player_tbl()
        self.player_table_id = player_table.id
        self.display_name = player_table.display_name
        self.avi_url = player_table.avi_url
        self._is_arp = player_table.is_auto_randpick
        self._is_arc = player_table.is_auto_randchoose
        self._is_dm_cards = player_table.is_dm_cards
        self._honorific = player_table.honorific
        # These are determined from each round, which might not be readily available upon player instantiation.
        #   Defaults are therefore used here.
        self._is_judge = False
        self._is_nuked_hand = False
        self._is_nuked_hand_caught = False

        self.game_id = None
        self.game_round_id = None

        self.pick_blocks = {}   # Provides a means for us to update a block kit ui upon a successful pick
        self.hand = Hand(owner=player_hash, eng=self.eng)

    @property
    def is_arp(self):
        return self._is_arp

    @is_arp.setter
    def is_arp(self, value):
        self._is_arp = value
        round_tbl = self._get_playerround_tbl()
        if round_tbl is not None and not round_tbl.is_picked:
            # They haven't yet picked, so they'd ARP this round too.
            #   Set that to make sure the data is logged properly
            self._set_player_round_tbl(TablePlayerRound.is_arp, self._is_arp)
        self._set_player_tbl(TablePlayer.is_auto_randpick, self._is_arp)

    @property
    def is_arc(self):
        return self._is_arc

    @is_arc.setter
    def is_arc(self, value):
        self.log.debug(f'Setting ARC to {value}')
        self._is_arc = value
        round_tbl = self._get_playerround_tbl()
        if round_tbl is not None:
            # No check here, as once a judge picks, the round progresses immediately
            self._set_player_round_tbl(TablePlayerRound.is_arc, self._is_arc)
        self._set_player_tbl(TablePlayer.is_auto_randchoose, self._is_arc)

    @property
    def is_dm_cards(self):
        return self._is_dm_cards

    @is_dm_cards.setter
    def is_dm_cards(self, value):
        self.log.debug(f'Setting DM cards to {value}')
        self._is_dm_cards = value
        self._set_player_tbl(TablePlayer.is_dm_cards, self._is_dm_cards)

    @property
    def honorific(self):
        return self._honorific

    @honorific.setter
    def honorific(self, value):
        self._honorific = value
        self._set_player_tbl(TablePlayer.honorific, self._honorific)

    @property
    def is_judge(self):
        return self._is_judge

    @is_judge.setter
    def is_judge(self, value):
        self._is_judge = value
        self._set_player_round_tbl(TablePlayerRound.is_judge, self._is_judge)

    @property
    def is_nuked_hand(self):
        return self._is_nuked_hand

    @is_nuked_hand.setter
    def is_nuked_hand(self, value):
        self._is_nuked_hand = value
        self._set_player_round_tbl(TablePlayerRound.is_nuked_hand, self._is_nuked_hand)

    @property
    def is_nuked_hand_caught(self):
        return self._is_nuked_hand_caught

    @is_nuked_hand_caught.setter
    def is_nuked_hand_caught(self, value):
        self._is_nuked_hand_caught = value
        self._set_player_round_tbl(TablePlayerRound.is_nuked_hand_caught, self._is_nuked_hand_caught)

    def _set_player_tbl(self, attr, value):
        with cah_app.eng.session_mgr() as session:
            session.query(TablePlayer).filter(TablePlayer.slack_user_hash == self.player_hash).update({
                attr: value
            })

    def _get_player_tbl(self) -> Optional[TablePlayer]:
        """Attempts to retrieve the player's info from the players table.
        if it doesnt exist, it creates a new row for the player."""
        with cah_app.eng.session_mgr() as session:
            tbl = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == self.player_hash).one_or_none()
            session.expunge(tbl)
        return tbl

    def _set_player_round_tbl(self, attr, value):
        with cah_app.eng.session_mgr() as session:
            session.query(TablePlayerRound).filter(and_(
                TablePlayerRound.game_key == self.game_id,
                TablePlayerRound.game_round_key == self.game_round_id
            )).join(TablePlayer, TablePlayerRound.player_key == TablePlayer.player_id).update({
                attr: value
            })

    def _get_playerround_tbl(self) -> TablePlayerRound:
        """Attempts to retrieve the player's info from the playerrounds table."""
        with cah_app.eng.session_mgr() as session:
            tbl = session.query(TablePlayerRound).filter(and_(
                TablePlayerRound.game_key == self.game_id,
                TablePlayerRound.game_round_key == self.game_round_id
            )).join(TablePlayer, TablePlayerRound.player_key == TablePlayer.player_id).one_or_none()
            session.expunge(tbl)
        return tbl

    def get_full_name(self) -> str:
        return self._get_player_tbl().full_name

    def start_round(self, game_id: int, game_round_id: int):
        """Begins a new round"""
        self.game_id = game_id
        self.game_round_id = game_round_id
        self.hand.pick.clear_picks()
        self._is_nuked_hand = False
        self._is_nuked_hand_caught = False
        with cah_app.eng.session_mgr() as session:
            session.add(TablePlayerRound(player_key=self.player_table_id, game_key=game_id,
                                         game_round_key=game_round_id, is_arp=self.is_arp, is_arc=self.is_arc))

    def toggle_cards_dm(self):
        """Toggles whether or not to DM cards to player"""
        self.is_dm_cards = not self.is_dm_cards

    def toggle_arp(self):
        """Toggles auto randpick"""
        self.is_arp = not self.is_arp

    def toggle_arc(self):
        """Toggles auto randpick"""
        self.is_arc = not self.is_arc

    def add_points(self, points: int):
        """Adds points to the player's score"""
        self._set_player_round_tbl(TablePlayerRound.score, TablePlayerRound.score + points)

    def get_current_score(self, game_id: int) -> int:
        """Retrieves the players current score"""
        with cah_app.eng.session_mgr() as session:
            return session.query(
                    func.sum(TablePlayerRound.score)
                ).filter(and_(
                    TablePlayerRound.player_key == self.player_table_id,
                    TablePlayerRound.game_key == game_id
                )).scalar()

    def get_honorific(self) -> str:
        pts = self.get_current_score(game_id=self.game_id)

        with self.eng.session_mgr() as session:
            honorific = session.query(TableHonorific).filter(and_(
                    pts >= TableHonorific.score_lower_lim,
                    pts <= TableHonorific.score_upper_lim
                )).order_by(func.random()).limit(1).one_or_none()
            session.expunge(honorific)
        if self.honorific != honorific.text:
            self.honorific = honorific.text
        return self.honorific

    def get_overall_score(self) -> int:
        """Retrieves the players current score"""
        tbl = self._get_player_tbl()
        return tbl.total_score


class Players:
    """Methods for handling all players"""
    def __init__(self, player_hash_list: List[str], slack_api: SlackTools, eng: WizzyPSQLClient, parent_log: Log):
        """
        Args:
            player_hash_list: list of player slack hashes
            slack_api: slack api to send messages to the channel
            parent_log: log object to record important details
        """
        self.log = Log(parent_log, child_name=self.__class__.__name__)
        self.st = slack_api
        self.eng = eng
        self.player_dict = {
            k: Player(k, eng=eng, log=self.log) for k in player_hash_list
        }  # type: Dict[str, Player]
        self.log.debug('Shuffling players and setting judge order')
        self.judge_order = player_hash_list
        shuffle(self.judge_order)

    def get_player_hashes(self) -> List[str]:
        """Collect user ids from a list of players"""
        return [k for k, v in self.player_dict.items()]

    def get_player_names(self, monospace: bool = False) -> List[str]:
        """Returns player display names"""
        if monospace:
            return [f'`{v.display_name}`' for k, v in self.player_dict.items()]
        return [v.display_name for k, v in self.player_dict.items()]

    def get_players_that_havent_picked(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of players that have yet to pick for the round"""
        players = [v for k, v in self.player_dict.items() if v.hand.pick.is_empty() and not v.is_judge]
        if name_only:
            return [x.display_name for x in players]
        else:
            return players

    def get_players_with_dm_cards(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_dm_cards turned on"""
        players = [v for k, v in self.player_dict.items() if v.is_dm_cards]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def get_players_with_arp(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_auto_randpick turned on"""
        players = [v for k, v in self.player_dict.items() if v.is_arp]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def get_players_with_arc(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_auto_randchoose turned on"""
        players = [v for k, v in self.player_dict.items() if v.is_arc]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def add_player_to_game(self, player_hash: str, game_id: int, game_round_id: int) -> str:
        """Adds a player to an existing game"""
        # Get the player's info
        self.log.debug('Beginning process to add player to game...')
        self.log.debug('Refreshing players in channel to scan for potential new players')
        refresh_players_in_channel(channel=auto_config.MAIN_CHANNEL, eng=self.eng, st=self.st, log=self.log)

        if self.player_dict.get(player_hash) is not None:
            return f'*`{self.player_dict[player_hash].display_name}`* already in game...'
        player = Player(player_hash=player_hash, log=self.log, eng=self.eng)
        player.start_round(game_id=game_id, game_round_id=game_round_id)
        self.player_dict[player_hash] = player
        self.judge_order.append(player_hash)
        self.log.debug(f'Player with name "{player.display_name}" added to game...')
        return f'*`{player.display_name}`* successfully added to game...'

    def remove_player_from_game(self, player_hash: str) -> str:
        """Removes a player from the existing game"""
        self.log.debug('Beginning process to remove player from game...')
        if self.player_dict.get(player_hash) is None:
            return f'That player is not in the current game...'
        self.log.debug(f'Removing player {player_hash} from game and judge order...')
        player = self.player_dict.pop(player_hash)
        # Remove from judge order
        _ = self.judge_order.pop(self.judge_order.index(player_hash))

        return f'*`{player.display_name}`* successfully removed from game...'

    def new_round(self, game_id: int, game_round_id: int):
        """Players-level new round routines"""
        self.log.debug('Handling player-level new round process')
        for p_hash, _ in self.player_dict.items():
            self.player_dict[p_hash].start_round(game_id=game_id, game_round_id=game_round_id)

    def render_hands(self, judge_hash: str, question_block: List[Dict], req_ans: int):
        """Renders each players' hands"""
        self.log.debug('Rendering hands for players...')
        for p_hash, p_obj in self.player_dict.items():
            if p_hash == judge_hash or p_obj.is_arp:
                continue
            cards_block = p_obj.hand.render_hand(max_selected=req_ans)  # type: List[Dict]
            if p_obj.is_dm_cards:
                msg_block = question_block + cards_block
                dm_chan, ts = self.st.private_message(p_hash, message='Here are your cards!', ret_ts=True,
                                                      blocks=msg_block)
                self.player_dict[p_hash].pick_blocks[dm_chan] = ts
            pchan_ts = self.st.private_channel_message(p_hash, auto_config.MAIN_CHANNEL, ret_ts=True,
                                                       message='Here are your cards!', blocks=cards_block)
            self.player_dict[p_hash].pick_blocks[auto_config.MAIN_CHANNEL] = pchan_ts

    def take_dealt_cards(self, player_hash: str, card_list: List['AnswerCard']):
        """Deals out cards to players"""
        for card in card_list:
            if card is None:
                continue
            self.player_dict[player_hash].hand.take_card(card)

    def reset_player_pick_block(self, player_hash: str):
        """Resets the dictionary containing info about the messsage containing pick info.
        This is run after updating the original message in order to ensure the no longer needed info is removed.
        """
        self.player_dict[player_hash].pick_blocks = {}

    def process_player_decknuke(self, player_hash: str):
        """Handles the player aspect of decknuking."""
        self.log.debug('Processing player decknuke')
        self.player_dict[player_hash].hand.burn_cards()
        self.player_dict[player_hash].is_nuked_hand = True


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_hash: str, eng: WizzyPSQLClient, log: Log):
        super().__init__(player_hash=player_hash, eng=eng, log=log)
        self.pick_idx = None    # type: Optional[int]
