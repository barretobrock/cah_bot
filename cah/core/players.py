#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from random import shuffle
from typing import (
    Dict,
    List,
    Optional,
    Union,
)

from loguru import logger
from slacktools import SlackTools
from slacktools.block_kit.base import BlocksType
from slacktools.block_kit.blocks import (
    ButtonSectionBlock,
    DividerBlock,
    MultiStaticSelectSectionBlock,
    SectionBlock,
)
from slacktools.block_kit.elements.display import PlainTextElement
from slacktools.block_kit.elements.input import ButtonElement
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import and_

from cah.core.common_methods import refresh_players_in_channel
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    SettingType,
    TableAnswerCard,
    TablePlayer,
    TablePlayerRound,
)
from cah.queries.player_queries import (
    PlayerHandCardType,
    PlayerQueries,
)


class Player:
    """Player-specific things"""

    def __init__(self, player_hash: str, eng: WizzyPSQLClient, log: logger):
        self.player_hash = player_hash
        self.player_tag = f'<@{self.player_hash}>'
        self.log = log.bind(child_name=self.__class__.__name__)
        self.pq = PlayerQueries(eng=eng, log=self.log)
        self.eng = eng

        player_table = self._get_player_tbl()
        self.player_table_id = player_table.player_id
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
        self._is_picked = False
        self._choice_order = player_table.choice_order  # type: Optional[int]

        self.game_id = None
        self.game_round_id = None

        self.pick_blocks = {}   # Provides a means for us to update a block kit ui upon a successful pick

    @property
    def is_arp(self) -> bool:
        return self._is_arp

    @is_arp.setter
    def is_arp(self, value: bool):
        self._is_arp = value
        round_tbl = self.get_playerround_tbl()
        if round_tbl is not None and not round_tbl.is_picked:
            # They haven't yet picked, so they'd ARP this round too.
            #   Set that to make sure the data is logged properly
            self._set_player_round_tbl(TablePlayerRound.is_arp, self._is_arp)
        self._set_player_tbl(TablePlayer.is_auto_randpick, self._is_arp)

    @property
    def is_arc(self) -> bool:
        return self._is_arc

    @is_arc.setter
    def is_arc(self, value: bool):
        self.log.debug(f'Setting ARC to {value}')
        self._is_arc = value
        round_tbl = self.get_playerround_tbl()
        if round_tbl is not None:
            # No check here, as once a judge picks, the round progresses immediately
            self._set_player_round_tbl(TablePlayerRound.is_arc, self._is_arc)
        self._set_player_tbl(TablePlayer.is_auto_randchoose, self._is_arc)

    @property
    def is_dm_cards(self) -> bool:
        return self._is_dm_cards

    @is_dm_cards.setter
    def is_dm_cards(self, value: bool):
        self.log.debug(f'Setting DM cards to {value}')
        self._is_dm_cards = value
        self._set_player_tbl(TablePlayer.is_dm_cards, self._is_dm_cards)

    @property
    def is_picked(self) -> bool:
        return self._is_picked

    @is_picked.setter
    def is_picked(self, value: bool):
        self.log.debug(f'Setting is_picked to {value}')
        self._is_picked = value
        round_tbl = self.get_playerround_tbl()
        if round_tbl is not None:
            # No check here, as once a judge picks, the round progresses immediately
            self._set_player_round_tbl(TablePlayerRound.is_picked, self._is_picked)

    @property
    def honorific(self) -> str:
        return self._honorific

    @honorific.setter
    def honorific(self, value: str):
        self._honorific = value
        self._set_player_tbl(TablePlayer.honorific, self._honorific)

    @property
    def choice_order(self) -> int:
        return self._choice_order

    @choice_order.setter
    def choice_order(self, value: int):
        self._choice_order = value
        self._set_player_tbl(TablePlayer.choice_order, self._choice_order)

    @property
    def is_judge(self) -> bool:
        return self._is_judge

    @is_judge.setter
    def is_judge(self, value: bool):
        self._is_judge = value
        self._set_player_round_tbl(TablePlayerRound.is_judge, self._is_judge)

    @property
    def is_nuked_hand(self) -> bool:
        return self._is_nuked_hand

    @is_nuked_hand.setter
    def is_nuked_hand(self, value: bool):
        self._is_nuked_hand = value
        self._set_player_round_tbl(TablePlayerRound.is_nuked_hand, self._is_nuked_hand)

    @property
    def is_nuked_hand_caught(self) -> bool:
        return self._is_nuked_hand_caught

    @is_nuked_hand_caught.setter
    def is_nuked_hand_caught(self, value: bool):
        self._is_nuked_hand_caught = value
        self._set_player_round_tbl(TablePlayerRound.is_nuked_hand_caught, self._is_nuked_hand_caught)

    def _set_player_tbl(self, attr: Union[InstrumentedAttribute, int, str], value: Optional[Union[int, bool, str]]):
        self.pq.set_player_table_attr(player_hash=self.player_hash, attr=attr, value=value)

    def _get_player_tbl(self) -> Optional[TablePlayer]:
        """Attempts to retrieve the player's info from the players table.
        if it doesnt exist, it creates a new row for the player."""
        return self.pq.get_player_table(player_hash=self.player_hash)

    def _set_player_round_tbl(self, attr: Union[InstrumentedAttribute, bool, int], value: Union[int, bool, str]):
        self.pq.set_player_round_table(player_id=self.player_table_id, game_round_id=self.game_round_id,
                                       game_id=self.game_id, attr=attr, value=value)

    def get_playerround_tbl(self) -> TablePlayerRound:
        """Attempts to retrieve the player's info from the playerrounds table."""
        return self.pq.get_player_round_table(player_id=self.player_table_id, game_round_id=self.game_round_id,
                                              game_id=self.game_id)

    def get_total_games_played(self) -> int:
        return self.pq.get_total_games_played(player_id=self.player_table_id)

    def get_total_decknukes_issued(self) -> int:
        return self.pq.get_total_decknukes_issued(player_id=self.player_table_id)

    def get_total_decknukes_caught(self) -> int:
        return self.pq.get_total_decknukes_caught(player_id=self.player_table_id)

    def get_full_name(self) -> str:
        return self._get_player_tbl().full_name

    def get_all_cards(self) -> int:
        """Marks all the cards in the hand as 'nuked' for a player who had chosen to 'decknuke' their cards"""
        return self.pq.get_all_cards(player_id=self.player_table_id)

    def get_nonreplaceable_cards(self) -> int:
        """Gets the cards in the deck that meet the criteria for being replaced
        (have been picked or have been nuked)"""
        return self.pq.get_nonreplaceable_cards(player_id=self.player_table_id)

    def nuke_cards(self):
        """Marks all the cards in the hand as 'nuked' for a player who had chosen to 'decknuke' their cards"""
        self.pq.set_nuke_cards(player_id=self.player_table_id)

    def take_cards(self, cards: List[TableAnswerCard]):
        """Takes a card into the player's hand"""
        self.pq.set_cards_in_hand(player_id=self.player_table_id, cards=cards)

    def get_hand(self) -> List:
        return self.pq.get_player_hand(player_id=self.player_table_id)

    def render_hand(self, max_selected: int = 1) -> BlocksType:
        """Renders the player's current hand to the player
        Args:
            max_selected: int, the maximum allowed number of definite selections (not randpicks) to make
                if this equals 1, the multi select for definite selections will not be rendered,
                otherwise it will take the place of the individual buttons
        """
        card_blocks = []
        btn_list = []  # Button info to be made into a button group
        randbtn_list = []  # Just like above, but bear a 'rand' prefix to differentiate. These can be subset.

        cards = self.get_hand()
        for i, card in enumerate(cards):
            num = i + 1
            # Make a dictionary to be used as an accessory to the card's text.
            #   If we need to pick more than one card for the question, set this dictionary as None
            #   so buttons don't get confusingly rendered next to the cards.
            #   (one of these buttons == one answer, so Wizzy will deny its entry as it's under the threshold)
            card_btn = ButtonElement(f'{num}', value=f'pick-{num}',
                                     action_id=f'game-pick-{num}') if max_selected == 1 else None
            card_blocks.append(
                SectionBlock(PlainTextElement(f'*{num}*: {card.card_text}'), accessory=card_btn)
            )
            # We'll still build this button list, as it's used below when we need to select multiple answers
            btn_list.append((f'{num}', f'pick-{num}'))
            randbtn_list.append((f'{num}', f'randpick-{num}'))

        # This is kinda hacky, but add the divider here so that if we don't have a multiselect area to add,
        #   we still have something to add to the return statement below to make the flow a bit better
        definite_selection_area = [
            DividerBlock()
        ]
        if max_selected > 1:
            desc = f'{max_selected} picks required for this question'
            definite_selection_area += [
                MultiStaticSelectSectionBlock(desc, btn_list, placeholder=f'Select {max_selected} picks',
                                              action_id='game-multipick', max_selected=max_selected),
                DividerBlock()
            ]

        rand_options = [('All picks', 'randpick-all')] + randbtn_list

        return card_blocks + definite_selection_area + [
            MultiStaticSelectSectionBlock('Randpick (all or subset)', placeholder='Select picks',
                                          option_pairs=rand_options, action_id='game-randpick'),
            ButtonSectionBlock('Force Close', 'Close', 'none', action_id='close')
        ]

    def pick_card(self, pos_list: List[int]) -> bool:
        """Picks cards at index(es)"""
        if self.is_picked or self.is_nuked_hand:
            # Already picked / nuked
            self.log.debug('Player already picked or nuked this round.')
            return False
        cards = self.get_hand()
        if not all([-1 < x < len(cards) for x in pos_list]):
            self.log.error(f'The positions in pos_list {pos_list} didn\'t match with the cards length '
                           f'({len(cards)})')
            return False
        # Assign picks
        for i, p in enumerate(pos_list):
            card = cards[p]  # type: PlayerHandCardType
            self.pq.set_picked_card(player_id=self.player_table_id, game_round_id=self.game_round_id,
                                    slack_user_hash=self.player_hash, position=i, card=card)
        return True

    def render_picks_as_str(self) -> str:
        """Grabs the player's picks and renders them in a pipe-delimited string in order that they were selected"""
        pick_strs = self.pq.get_picks_as_str(player_id=self.player_table_id, game_round_id=self.game_round_id)
        return f'`{"` | `".join(pick_strs)}`'

    def start_round(self, game_id: int, game_round_id: int):
        """Begins a new round"""
        self.game_id = game_id
        self.game_round_id = game_round_id
        # self.hand.pick.clear_picks()
        # Reset round-specific variables
        self._is_nuked_hand = False
        self._is_nuked_hand_caught = False
        self._is_picked = False
        self._choice_order = None
        self.pq.handle_player_new_round(player_id=self.player_table_id, game_round_id=game_round_id,
                                        game_id=game_id, is_arc=self.is_arc, is_arp=self.is_arp)

    def mark_chosen_pick(self):
        """When a pick is chosen by a judge, this method handles marking those cards as chosen in the db
        for better tracking"""
        self.pq.mark_chosen_pick(player_id=self.player_table_id, game_round_id=self.game_round_id)

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

    def get_current_score(self) -> int:
        """Retrieves the players current score"""
        return self.pq.get_current_score(game_id=self.game_id, player_id=self.player_table_id)

    def get_honorific(self) -> str:
        """Retrieves a (potentially refreshed) honorific"""
        pts = self.get_current_score()
        honorific = self.pq.get_honorific(points=pts)

        if self.honorific != honorific:
            self.log.debug('Player\'s honorific was updated.')
            self.honorific = honorific
        return self.honorific

    def get_overall_score(self) -> int:
        """Retrieves the players current score"""
        return self.pq.get_overall_score(player_id=self.player_table_id)


class Players:
    """Methods for handling all players"""
    judge_order: List[str]
    player_dict = Dict[str, Player]

    def __init__(self, player_hash_list: List[str], slack_api: SlackTools, eng: WizzyPSQLClient,
                 parent_log: logger, config, is_existing: bool = False):
        """
        Args:
            player_hash_list: list of player slack hashes
            slack_api: slack api to send messages to the channel
            parent_log: log object to record important details
        """
        self.log = parent_log.bind(child_name=self.__class__.__name__)
        self.st = slack_api
        self.eng = eng
        self.config = config
        self.player_dict = {
            k: Player(k, eng=eng, log=self.log) for k in player_hash_list
        }

        if not is_existing:
            self.log.debug('Shuffling players and setting judge order')
            self.judge_order = player_hash_list
            shuffle(self.judge_order)
            self.eng.set_setting(SettingType.JUDGE_ORDER, setting_val=','.join(self.judge_order))
        else:
            self.judge_order = self.eng.get_setting(SettingType.JUDGE_ORDER).split(',')

    def reinstate_round_players(self, game_id: int, game_round_id: int):
        """Handles the player side of reinstating the game / round"""
        # For each participating player, load the game id and game round id
        for uid, player in self.player_dict.items():
            player.game_id = game_id
            player.game_round_id = game_round_id
            # Populate the player's object with info from the round table
            player_round_tbl: TablePlayerRound
            player_round_tbl = player.get_playerround_tbl()
            player._is_judge = player_round_tbl.is_judge
            player._is_nuked_hand = player_round_tbl.is_nuked_hand
            player._is_nuked_hand_caught = player_round_tbl.is_nuked_hand_caught
            player._is_picked = player_round_tbl.is_picked

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
        players = [v for k, v in self.player_dict.items() if not v.is_picked and not v.is_judge]
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
        refresh_players_in_channel(channel=self.config.MAIN_CHANNEL, eng=self.eng, st=self.st, log=self.log)

        if self.player_dict.get(player_hash) is not None:
            return f'*`{self.player_dict[player_hash].display_name}`* already in game...'
        player = Player(player_hash=player_hash, log=self.log, eng=self.eng)
        player.start_round(game_id=game_id, game_round_id=game_round_id)
        self.player_dict[player_hash] = player
        self.judge_order.append(player_hash)
        self.eng.set_setting(SettingType.JUDGE_ORDER, setting_val=','.join(self.judge_order))
        self.log.debug(f'Player with name "{player.display_name}" added to game...')
        return f'*`{player.display_name}`* successfully added to game...'

    def remove_player_from_game(self, player_hash: str) -> str:
        """Removes a player from the existing game"""
        self.log.debug('Beginning process to remove player from game...')
        if self.player_dict.get(player_hash) is None:
            return 'That player is not in the current game...'
        self.log.debug(f'Removing player {player_hash} from game and judge order...')
        player = self.player_dict.pop(player_hash)
        # Remove from judge order
        _ = self.judge_order.pop(self.judge_order.index(player_hash))
        self.eng.set_setting(SettingType.JUDGE_ORDER, setting_val=','.join(self.judge_order))

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
            cards_block = p_obj.render_hand(max_selected=req_ans)  # type: List[Dict]
            if p_obj.is_dm_cards:
                msg_block = question_block + cards_block
                dm_chan, ts = self.st.private_message(p_hash, message='Here are your cards!', ret_ts=True,
                                                      blocks=msg_block)
                self.player_dict[p_hash].pick_blocks[dm_chan] = ts
            pchan_ts = self.st.private_channel_message(p_hash, self.config.MAIN_CHANNEL, ret_ts=True,
                                                       message='Here are your cards!', blocks=cards_block)
            self.player_dict[p_hash].pick_blocks[self.config.MAIN_CHANNEL] = pchan_ts

    def take_dealt_cards(self, player_hash: str, card_list: List[TableAnswerCard]):
        """Deals out cards to players"""
        self.player_dict[player_hash].take_cards(card_list)

    def reset_player_pick_block(self, player_hash: str):
        """Resets the dictionary containing info about the messsage containing pick info.
        This is run after updating the original message in order to ensure the no longer needed info is removed.
        """
        self.player_dict[player_hash].pick_blocks = {}

    def process_player_decknuke(self, player_hash: str):
        """Handles the player aspect of decknuking."""
        self.log.debug('Processing player decknuke')
        self.player_dict[player_hash].nuke_cards()
        self.player_dict[player_hash].is_nuked_hand = True


class Judge(Player):
    """Player who chooses winning card"""
    def __init__(self, player_hash: str, eng: WizzyPSQLClient, log: logger):
        super().__init__(player_hash=player_hash, eng=eng, log=log)
        self.selected_choice_idx = None  # type: Optional[int]
        self.winner_id = None    # type: Optional[int]
        self.winner_hash = None  # type: Optional[str]
        self._choice_order = None

    def get_winner_from_choice_order(self):
        """Obtains winner's player id from the choice"""
        with self.eng.session_mgr() as session:
            winner: TablePlayer
            winner = session.query(TablePlayer).filter(and_(
                TablePlayer.choice_order == self.selected_choice_idx,
                TablePlayer.is_active
            )).one()
            if winner is not None:
                self.log.debug(f'Selected winner: {winner}')
                self.winner_id = winner.player_id
                self.winner_hash = winner.slack_user_hash
