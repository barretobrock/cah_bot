#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from typing import List, Optional, Union, Dict
from sqlalchemy.orm.session import Session
from easylogger import Log
from slacktools import SlackTools
import cah.cards as cahds
from .settings import auto_config
from .model import TablePlayers, TablePlayerRounds


class Player:
    """Player-specific things"""

    def __init__(self, player_id: str, display_name: str, session: Session):
        self.player_id = player_id
        self.player_tag = f'<@{self.player_id}>'
        self.display_name = display_name
        self.session = session

        self.player_table = self.session.query(TablePlayers)\
            .filter_by(slack_id=self.player_id).one_or_none()   # type: TablePlayers
        if self.player_table is None:
            # Add player to table
            self.player_table = self.session.add(TablePlayers(slack_id=self.player_id, name=self.display_name))
            self.session.commit()

        # For tracking rounds that the player plays. This will be None until the player is loaded into a game
        self.player_round_table = None  # type: Optional[TablePlayerRounds]

        self.pick_blocks = {}   # Provides a means for us to update a block kit ui upon a successful pick
        self.hand = cahds.Hand(owner=self.player_table, session=self.session)

    def start_round(self, game_id: int, round_id: int):
        """Begins a new round"""
        self.hand.pick.clear_picks()
        self.player_round_table = TablePlayerRounds(player_id=self.player_id, game_id=game_id, round_id=round_id)
        self.session.commit()

    def toggle_cards_dm(self):
        """Toggles whether or not to DM cards to player"""
        self.player_table.is_dm_cards = not self.player_table.is_dm_cards
        self.session.commit()

    def toggle_arp(self):
        """Toggles auto randpick"""
        self.player_table.is_auto_randpick = not self.player_table.is_auto_randpick
        self.session.commit()

    def toggle_arc(self):
        """Toggles auto randpick"""
        self.player_table.is_auto_randchoose = not self.player_table.is_auto_randchoose
        self.session.commit()

    def add_points(self, points: int):
        """Adds points to the player's score"""
        self.player_round_table.score += points
        self.session.commit()


class Players:
    """Methods for handling all players"""
    def __init__(self, player_id_list: List[str], session: Session, slack_api: SlackTools, parent_log: Log):
        """

        """
        self.player_list = self._build_players(player_id_list=player_id_list)
        self.session = session
        self.st = slack_api
        self.log = Log(parent_log, child_name=self.__class__.__name__)

    @staticmethod
    def _extract_name(user_info_dict: Dict[str, str]) -> str:
        return user_info_dict['display_name'] if user_info_dict['display_name'] != '' else user_info_dict['name']

    def _build_players(self, player_id_list: List[str]) -> List[Player]:
        """Builds out the list of players - Typically used when a new game is started"""
        players = []
        for user in self.st.get_channel_members(auto_config.MAIN_CHANNEL, humans_only=True):
            uid = user['id']
            if uid in player_id_list:
                # Make sure display name is not empty
                dis_name = self._extract_name(user_info_dict=user)

                if self.session.query(TablePlayers).filter_by(slack_id=uid).one_or_none() is None:
                    # Add missing player to
                    self.log.debug(f'Player {dis_name} was not found in the players table. Adding...')
                    self.session.add(TablePlayers(slack_id=uid, name=dis_name))
                players.append(Player(uid, display_name=dis_name, session=self.session))
        self.session.commit()
        return players

    def get_player_ids(self) -> List[str]:
        """Collect user ids from a list of players"""
        return [x.player_id for x in self.player_list]

    def get_player_names(self, monospace: bool = False) -> List[str]:
        """Returns player display names"""
        if monospace:
            return [f'`{x.player_table.display_name}`' for x in self.player_list]
        return [x.player_table.display_name for x in self.player_list]

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
        players = [x for x in self.player_list if x.hand.pick.is_empty() and not x.player_round_table.is_judge]
        if name_only:
            return [x.player_table.display_name for x in players]
        else:
            return players

    def add_player_to_game(self, player_id: str):
        """Adds a player to an existing game"""
        # Get the player's info
        user_info = self.st.get_users_info([player_id])[0]
        dis_name = self._extract_name(user_info_dict=user_info)

        if self.session.query(TablePlayers).filter_by(slack_id=player_id).one_or_none() is None:
            # Add missing player to
            self.log.debug(f'Player {dis_name} was not found in the players table. Adding...')
            self.session.add(TablePlayers(slack_id=player_id, name=dis_name))

        self.player_list.append(Player(player_id, display_name=dis_name, session=self.session))
        self.session.commit()

    def remove_player_from_game(self, player_id: str):
        """Removes a player from the existing game"""
        # Get player's index in list
        pidx = self.get_player_index(player_attr=player_id, attr_name='player_id')
        _ = self.player_list.pop(pidx)
        self.log.debug(f'Player with id "{player_id}" removed from game...')

    def new_round(self, game_id: int, round_id: int):
        """Players-level new round routines"""
        for player in self.player_list:
            player.start_round(game_id=game_id, round_id=round_id)
            self._update_player(player)

    def take_dealt_cards(self, player_obj: Player, card_list: List[cahds.AnswerCard]):
        """Deals out cards to players"""
        for card in card_list:
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
        player_obj.hand.burn_cards()
        player_obj.player_round_table.is_nuked_hand = True
        self._update_player(player_obj)


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_id: str, display_name: str, session: Session):
        super().__init__(player_id, display_name=display_name, session=session)
        self.pick_idx = None    # type: Optional[int]
