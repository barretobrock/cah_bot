#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
from typing import List, Optional, Union
from .cards import Hand


class Player:
    """Player-specific things"""

    def __init__(self, player_id: str, display_name: str):
        self.player_id = player_id
        self.player_tag = f'<@{self.player_id}>'
        self.is_judge = False
        self.honorific = ''
        self.display_name = display_name
        self.dm_cards = True
        self.skip = False
        self.auto_randpick = False
        self.auto_randchoose = False
        self.voted = False
        self.nuked_hand = False   # If set to true, dealt entire new hand next round
        self.pick_blocks = {}   # Provides a means for us to update a block kit ui upon a successful pick
        self.vote_blocks = {}
        self.hand = Hand(owner=self.player_id)
        # Ending scores for games
        self.final_scores = list()
        # Current game score
        self.points = 0
        self.rounds_played = 0

    def toggle_cards_dm(self):
        """Toggles whether or not to DM cards to player"""
        self.dm_cards = not self.dm_cards

    def get_last_game_score(self) -> int:
        """Retrieves the score from the last game"""
        return self.final_scores[-1] if len(self.final_scores) > 0 else 0

    def get_grand_score(self) -> int:
        """Retrieves the overall score from all games"""
        return sum(self.final_scores)

    def get_cumulative_score(self) -> str:
        """Retrieves the cumulative scores from all games"""
        return ', '.join([f'{x}' for x in np.cumsum(self.final_scores)])

    def add_points(self, points: int):
        """Adds points to the player's score"""
        self.points += points


class Players:
    """Methods for handling all players"""
    def __init__(self, player_list: List[Player], origin: str = 'channel'):
        """
        :param player_list: list of dict, players in channel
        """
        if origin == 'channel':
            self.player_list = self.load_players_in_channel(player_list)
        else:
            # Already built Player objects, likely loading into a game
            self.player_list = player_list
        self.eligible_players = None

    def load_players_in_channel(self, player_list: List[Player], refresh: bool = False,
                                names_only: bool = False) -> Optional[List[Player]]:
        """Loads all the human players in the channel from a list of dicts containing channel member info"""
        if refresh:
            # Check if someone hasn't yet been added, but preserve other players' details
            for p in player_list:
                if self.get_player_index_by_id(p.player_id) is None:
                    # Player not in list
                    self.player_list.append(Player(p.player_id, p.display_name))
                else:
                    player = self.get_player_by_id(p.player_id)
                    # Ensure the display_name is up to date
                    player.display_name = p.display_name
                    if not names_only:
                        # Reset basic info
                        player.skip = False
                        player.hand = Hand(owner=player.player_id)
        else:
            plist = []
            for p in player_list:
                plist.append(Player(p.player_id, p.display_name))
            return plist

    def get_player_ids(self) -> List[str]:
        """Collect user ids from a list of players"""
        return [x.player_id for x in self.player_list]

    def get_player_names(self) -> List[str]:
        """Returns player display names"""
        return [x.display_name for x in self.player_list]

    def get_player_names_monospace(self) -> List[str]:
        """Returns player display names formatted for Slack's monospace"""
        return [f'`{x}`' for x in self.get_player_names()]

    def get_player_index_by_id(self, player_id: str) -> Optional[int]:
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        matches = [x for x in self.player_list if x.player_id == player_id]
        if len(matches) > 0:
            return self.player_list.index(matches[0])
        return None

    def get_player_index_by_tag(self, player_tag: str) -> Optional[int]:
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        matches = [x for x in self.player_list if x.player_tag == player_tag]
        if len(matches) > 0:
            return self.player_list.index(matches[0])
        return None

    def get_player_by_id(self, player_id: str) -> Optional[Player]:
        """Returns a Player object that has a matching 'id' value in a list of players"""
        player_idx = self.get_player_index_by_id(player_id)
        if player_idx is not None:
            return self.player_list[player_idx]
        return None

    def get_player_by_tag(self, tag: str) -> Optional[Player]:
        """Returns a Player object that has a matching tag (e.g., '<@{id}>') in a list of players"""
        player_idx = self.get_player_index_by_tag(tag)
        if player_idx is not None:
            return self.player_list[player_idx]
        return None

    def update_player(self, player_obj: Player):
        """Updates the player's object by finding its position in the player list"""
        player_idx = self.get_player_index_by_id(player_obj.player_id)
        self.player_list[player_idx] = player_obj

    def skip_player_by_tag_or_id(self, player_tag_or_id: str):
        """Set player's skip attribute to True if their tag or id matches"""
        use_tag = '<@' in player_tag_or_id
        for player in self.player_list:
            if use_tag:
                if player.player_tag == player_tag_or_id:
                    player.skip = True
            else:
                if player.player_id == player_tag_or_id:
                    player.skip = True

    def skip_players_not_in_list(self, player_ids: List[str]):
        """Assigns skip attribute to True for players that don't have an id in the list provided"""
        for player in self.player_list:
            # Skip player if not in our list of ids
            player.skip = player.player_id not in player_ids

    def skip_players_in_list(self, player_ids: List[str]):
        """Assigns skip attribute to True for player ids in the list provided"""
        for player in self.player_list:
            # Skip player if not in our list of ids
            player.skip = player.player_id in player_ids

    def set_eligible_players(self):
        """Sets list of eligible players"""
        self.eligible_players = [x for x in self.player_list if not x.skip]

    def have_all_players_voted(self) -> bool:
        """Determines if all non-judge players have voted"""
        return all([x.voted for x in self.player_list if not x.is_judge])


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_id: str, display_name: str):
        super().__init__(player_id, display_name)
        self.pick_idx = None
