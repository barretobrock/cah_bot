#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import (
    List,
    Optional,
    Union,
    Dict,
    TYPE_CHECKING
)
from sqlalchemy.sql import (
    func,
    and_
)
from easylogger import Log
from slacktools import SlackTools
import cah.app as cah_app
from cah.model import (
    TablePlayer,
    TablePlayerRound
)
from cah.settings import auto_config
if TYPE_CHECKING:
    from cah.cards import AnswerCard


class Player:
    """Player-specific things"""

    def __init__(self, player_hash: str, display_name: str, avi_url: str, log: Log):
        self.player_hash = player_hash
        self.player_tag = f'<@{self.player_hash}>'
        self.display_name = display_name
        self.log = log
        self.avi_url = avi_url

        player_table = self._get_player_tbl()
        self.player_table_id = player_table.id

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
        self.hand = cahds.Hand(owner=player_hash)

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

    def start_round(self, game_id: int, game_round_id: int):
        """Begins a new round"""
        self.game_id = game_id
        self.game_round_id = game_round_id
        self.hand.pick.clear_picks()
        self._is_nuked_hand = False
        self._is_nuked_hand_caught = False
        with cah_app.eng.session_mgr() as session:
            session.add(TablePlayerRound(player_key=self.player_table_id, game_key=game_id,
                                         game_round_key=game_round_id, is_arp=self.is_arp,is_arc=self.is_arc))

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

    def get_full_name(self) -> str:
        """Combines the player's name with their honorific"""
        return f'{self.display_name.title()} {self.honorific.title()}'

    def get_current_score(self, game_id: int) -> int:
        """Retrieves the players current score"""
        with cah_app.eng.session_mgr() as session:
            return session.query(
                    func.sum(TablePlayerRound.score)
                ).filter(and_(
                    TablePlayerRound.player_key == self.player_table_id,
                    TablePlayerRound.game_key == game_id
                )).scalar()

    def get_overall_score(self) -> int:
        """Retrieves the players current score"""
        tbl = self._get_player_tbl()
        return tbl.total_score


class Players:
    """Methods for handling all players"""
    def __init__(self, player_id_list: List[str], slack_api: SlackTools, parent_log: Log, is_global: bool = False):
        """
        Args:
            player_id_list: list of player slack ids
            slack_api: slack api to send messages to the channel
            parent_log: log object to record important details
            is_global: if True, players will be built according to active workspace members,
                not necessarily only channel members
        """
        self.log = Log(parent_log, child_name=self.__class__.__name__)
        self.st = slack_api
        self.is_global = is_global
        self.player_list = self._build_players(player_id_list=player_id_list)

    @staticmethod
    def _extract_name(user_info_dict: Dict[str, str]) -> str:
        return user_info_dict['display_name'] if user_info_dict['display_name'] != '' else user_info_dict['name']

    def _check_player_existence_in_table(self, user_id: str, display_name: str):
        """Checks whether player exists in the player table and, if not, will add them to the table"""
        # Check if player table exists
        self.log.debug('Checking for player\'s existence in table')
        player_table = cah_app.db.session.query(TablePlayer).filter_by(slack_id=user_id).one_or_none()

        if player_table is None:
            # Add missing player to
            self.log.debug(f'Player {display_name} was not found in the players table. Adding...')
            cah_app.db.session.add(TablePlayer(slack_id=user_id, name=display_name))
        cah_app.db.session.commit()

    def _build_players(self, player_id_list: List[str]) -> List[Player]:
        """Builds out the list of players - Typically used when a new game is started"""
        self.log.debug('Starting player building process.')
        players = []
        channel_members = self.st.get_channel_members(auto_config.MAIN_CHANNEL, humans_only=True)
        for user in channel_members:
            uid = user['id']
            if uid in player_id_list:
                # Make sure display name is not empty
                dis_name = self._extract_name(user_info_dict=user)
                # Make sure player is in table
                self._check_player_existence_in_table(user_id=uid, display_name=dis_name)
                players.append(Player(uid, display_name=dis_name, avi_url=user['avi32']))
        if not self.is_global:
            # Building players specifically for a game, so determine if we included people
            #   that aren't currently members
            # Determine missed users
            missed_users = [x for x in player_id_list if x not in [y.player_id for y in players]]
            if len(missed_users) > 0:
                # Message channel about missing users
                usr_tags = ', '.join([f'<@{x.upper()}>' for x in missed_users])
                msg = f'These users aren\'t in the channel and therefore were skipped: {usr_tags}'
                self.st.send_message(auto_config.MAIN_CHANNEL, msg)
        return players

    def get_player_ids(self) -> List[str]:
        """Collect user ids from a list of players"""
        return [x.player_id for x in self.player_list]

    def get_player_names(self, monospace: bool = False) -> List[str]:
        """Returns player display names"""
        if monospace:
            return [f'`{x.display_name}`' for x in self.player_list]
        return [x.display_name for x in self.player_list]

    def get_player_index(self, player_attr: str, attr_name: str = 'player_id') -> Optional[int]:
        """Returns the index of a player in a list of players based on a given attribute"""
        player = self.get_player(player_attr=player_attr, attr_name=attr_name)

        if player is not None:
            return self.player_list.index(player)
        return None

    def get_player(self, player_attr: str, attr_name: str = 'player_id') -> Optional[Player]:
        """Returns a Player object that has a matching attribute value from a list of players"""
        matches = [x for x in self.player_list if x.__getattribute__(attr_name) == player_attr]
        if len(matches) > 0:
            return matches[0]
        return None

    def _update_player(self, player_obj: Player):
        """Updates the player's object by finding its position in the player list and replacing it"""
        player_idx = self.get_player_index(player_obj.player_id, attr_name='player_id')
        self.player_list[player_idx] = player_obj

    def get_players_that_havent_picked(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of players that have yet to pick for the round"""
        players = [x for x in self.player_list if x.hand.pick.is_empty() and not x.is_judge]
        if name_only:
            return [x.display_name for x in players]
        else:
            return players

    def get_players_with_dm_cards(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_dm_cards turned on"""
        players = [x for x in self.player_list if x.is_dm_cards]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def get_players_with_arp(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_auto_randpick turned on"""
        players = [x for x in self.player_list if x.is_arp]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def get_players_with_arc(self, name_only: bool = True) -> List[Union[str, Player]]:
        """Returns a list of names (monospaced) or players that have is_auto_randchoose turned on"""
        players = [x for x in self.player_list if x.is_arc]
        if name_only:
            return [f'`{x.display_name}`' for x in players]
        return players

    def add_player_to_game(self, player_id: str, game_id: int, round_id: int) -> str:
        """Adds a player to an existing game"""
        # Get the player's info
        self.log.debug('Beginning process to add player to game...')
        user_info = self.st.clean_user_info(self.st.get_user_info(player_id).get('user'))
        dis_name = self._extract_name(user_info_dict=user_info)

        # Make sure player is in table
        self._check_player_existence_in_table(user_id=player_id, display_name=dis_name)
        # Make sure player is not already in game
        player = self.get_player(player_id)
        if player is not None:
            return f'*`{dis_name}`* already in game...'
        player = Player(player_id, display_name=dis_name, avi_url=user_info['avi32'])
        player.start_round(game_id=game_id, round_id=round_id)
        self.player_list.append(player)
        self.log.debug(f'Player with name "{dis_name}" added to game...')
        return f'*`{dis_name}`* successfully added to game...'

    def remove_player_from_game(self, player_id: str) -> str:
        """Removes a player from the existing game"""
        self.log.debug('Beginning process to remove player from game...')
        # Get player's index in list
        player = self.get_player(player_id)
        if player is None:
            return f'That player is not in the current game...'
        pidx = self.get_player_index(player_attr=player_id, attr_name='player_id')
        _ = self.player_list.pop(pidx)
        self.log.debug(f'Player with name "{player.display_name}" removed from game...')
        return f'*`{player.display_name}`* successfully removed from game...'

    def new_round(self, game_id: int, round_id: int):
        """Players-level new round routines"""
        self.log.debug('Handling player-level new round process')
        for player in self.player_list:
            player.start_round(game_id=game_id, round_id=round_id)
            self._update_player(player)

    def render_hands(self, judge_id: str, question_block: List[Dict], req_ans: int):
        """Renders each players' hands"""
        self.log.debug('Rendering hands for players...')
        for player in self.player_list:
            if player.player_id == judge_id or player.is_arp:
                continue
            cards_block = player.hand.render_hand(max_selected=req_ans)  # type: List[Dict]
            if player.is_dm_cards:
                msg_block = question_block + cards_block
                dm_chan, ts = self.st.private_message(player.player_id, message='', ret_ts=True,
                                                      blocks=msg_block)
                player.pick_blocks[dm_chan] = ts
            pchan_ts = self.st.private_channel_message(player.player_id, auto_config.MAIN_CHANNEL, ret_ts=True,
                                                       message='', blocks=cards_block)
            player.pick_blocks[auto_config.MAIN_CHANNEL] = pchan_ts

            self._update_player(player)

    def take_dealt_cards(self, player_obj: Player, card_list: List['AnswerCard']):
        """Deals out cards to players"""
        for card in card_list:
            if card is None:
                continue
            player_obj.hand.take_card(card)
        self._update_player(player_obj)

    def reset_player_pick_block(self, player_obj: Player):
        """Resets the dictionary containing info about the messsage containing pick info.
        This is run after updating the original message in order to ensure the no longer needed info is removed.
        """
        player_obj.pick_blocks = {}
        self._update_player(player_obj=player_obj)

    def process_player_decknuke(self, player_obj: Player):
        """Handles the player aspect of decknuking."""
        self.log.debug('Processing player decknuke')
        player_obj.hand.burn_cards()
        player_obj.is_nuked_hand = True
        self._update_player(player_obj)


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_obj: Player):
        super().__init__(player_obj.player_id, display_name=player_obj.display_name)
        self.pick_idx = None    # type: Optional[int]
