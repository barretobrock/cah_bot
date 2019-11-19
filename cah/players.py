#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
from .cards import Hand


class Players:
    """Methods for handling all players"""
    def __init__(self, player_list, origin='channel'):
        """
        :param player_list: list of dict, players in channel
        """
        if origin == 'channel':
            self.player_list = self.load_players_in_channel(player_list)
        else:
            # Already built Player objects, likely loading into a game
            self.player_list = player_list
        self.eligible_players = None

    def load_players_in_channel(self, player_list, refresh=False, names_only=False):
        """Loads all the human players in the channel from a list of dicts containing channel member info"""
        if refresh:
            # Check if someone hasn't yet been added, but preserve other players' details
            for p in player_list:
                if self.get_player_index_by_id(p['id']) is None:
                    # Player not in list
                    self.player_list.append(Player(p['id'], p['display_name']))
                else:
                    player = self.get_player_by_id(p['id'])
                    # Ensure the display_name is up to date
                    player.display_name = p['display_name']
                    if not names_only:
                        # Reset basic info
                        player.skip = False
                        player.pick = None
                        player.hand = Hand()
        else:
            plist = []
            for p in player_list:
                plist.append(Player(p['id'], p['display_name']))
            return plist

    def get_player_ids(self):
        """Collect user ids from a list of players"""
        return [x.player_id for x in self.player_list]

    def get_player_names(self):
        """Returns player display names"""
        return [x.display_name for x in self.player_list]

    def get_player_index_by_id(self, player_id):
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        matches = [x for x in self.player_list if x.player_id == player_id]
        if len(matches) > 0:
            return self.player_list.index(matches[0])
        return None

    def get_player_index_by_tag(self, player_tag):
        """Returns the index of a player in a list of players that has a matching 'id' value"""
        matches = [x for x in self.player_list if x.player_tag == player_tag]
        if len(matches) > 0:
            return self.player_list.index(matches[0])
        return None

    def get_player_by_id(self, player_id):
        """Returns a Player object that has a matching 'id' value in a list of players"""
        player_idx = self.get_player_index_by_id(player_id)
        if player_idx is not None:
            return self.player_list[player_idx]
        return None

    def get_player_by_tag(self, tag):
        """Returns a Player object that has a matching tag (e.g., '<@{id}>') in a list of players"""
        player_idx = self.get_player_index_by_tag(tag)
        if player_idx is not None:
            return self.player_list[player_idx]
        return None

    def update_player(self, player_obj):
        """Updates the player's object by finding its position in the player list"""
        player_idx = self.get_player_index_by_id(player_obj.player_id)
        self.player_list[player_idx] = player_obj

    def skip_player_by_tag_or_id(self, player_tag_or_id):
        """Set player's skip attribute to True if their tag or id matches"""
        use_tag = '<@' in player_tag_or_id
        for player in self.player_list:
            if use_tag:
                if player.player_tag == player_tag_or_id:
                    player.skip = True
            else:
                if player.player_id == player_tag_or_id:
                    player.skip = True

    def skip_players_not_in_list(self, player_ids):
        """Assigns skip attribute to True for players that don't have an id in the list provided"""
        for player in self.player_list:
            # Skip player if not in our list of ids
            player.skip = player.player_id not in player_ids

    def set_eligible_players(self):
        """Sets list of eligible players"""
        self.eligible_players = [x for x in self.player_list if not x.skip]


class Player:
    """Player-specific things"""

    def __init__(self, player_id, display_name):
        self.player_id = player_id
        self.player_tag = '<@{}>'.format(self.player_id)
        self.display_name = display_name
        self.dm_cards = False
        self.skip = False
        self.pick = None
        self.hand = Hand()
        # Ending scores for games
        self.final_scores = list()
        # Current game score
        self.points = 0

    def toggle_cards_dm(self):
        """Toggles whether or not to DM cards to player"""
        self.dm_cards = not self.dm_cards

    def get_last_game_score(self):
        """Retrieves the score from the last game"""
        return self.final_scores[-1] if len(self.final_scores) > 0 else 0

    def get_grand_score(self):
        """Retrieves the overall score from all games"""
        return sum(self.final_scores)

    def get_cumulative_score(self):
        """Retrieves the cumulative scores from all games"""
        return ', '.join(['{}'.format(x) for x in np.cumsum(self.final_scores)])


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_id, display_name):
        super().__init__(player_id, display_name)
