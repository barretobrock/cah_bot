from typing import (
    TYPE_CHECKING,
    List,
)

from loguru import logger
from slacktools import SlackTools
from slacktools.block_kit.base import BlocksType
from slacktools.block_kit.blocks import (
    ActionsBlock,
    MultiUserSelectSectionBlock,
    PlainTextHeaderBlock,
    PlainTextInputBlock,
    PlainTextSectionBlock,
    StaticSelectSectionBlock,
    UserSelectSectionBlock,
)
from slacktools.block_kit.elements.input import (
    ButtonElement,
    ConfirmElement,
)
from sqlalchemy.sql import (
    and_,
    func,
)

from cah.db_eng import WizzyPSQLClient
from cah.model import (
    GameStatus,
    TablePlayer,
    TablePlayerRound,
)

if TYPE_CHECKING:
    from cah.core.games import Game


class Forms:
    """Stores various Block Kit forms"""
    def __init__(self, st: SlackTools, eng: WizzyPSQLClient):
        self.st = st
        self.eng = eng

    def build_main_menu(self, game_obj: 'Game', user: str, channel: str):
        """Generates and sends a main menu"""
        logger.debug(f'Received menu command from {user} in {channel}. Building menu.')
        game_is_ongoing = game_obj is not None and game_obj.status not in [GameStatus.ENDED]

        end_game_confirm = ConfirmElement('Really end game??',
                                          'Awe youwu weawwy suwe youwu want to end :nervous-plead:?',
                                          'Ya', 'Na')
        main_buttons = [
            ButtonElement('New Game', value='newgame', action_id='new-game-start', style='primary'),
            ButtonElement('End Game', value='end-game', action_id='end-game', style='danger',
                          confirm=end_game_confirm),
            ButtonElement('Close', value='close', action_id='close')
        ]

        game_info_buttons = [
            ButtonElement('Status', value='status', action_id='status'),
            ButtonElement('Scores', value='score', action_id='score'),
            ButtonElement('Game Stats', value='game-stats', action_id='game-stats')
        ]

        game_action_buttons = []
        if game_is_ongoing:
            game_action_buttons += [
                ButtonElement('Ping Ppl', value='ping', action_id='ping'),
                ButtonElement('Modify Question', value='mod-question', action_id='modify-question-form')
            ]

        player_info_buttons = [
            ButtonElement('My Stats', value='my-stats', action_id='my-stats'),
            ButtonElement('Player Stats', value='player-stats', action_id='player-stats')
        ]

        player_action_buttons = [
            ButtonElement('My Settings', value='my-settings', action_id='my-settings'),
            ButtonElement('ARP/ARC Player', value='arparc-player', action_id='arparc-player'),
            ButtonElement('Add Player', value='add-player', action_id='add-player'),
            ButtonElement('Kick Player', value='remove-player', action_id='remove-player', confirm=ConfirmElement(
                'Really kick someone off the game??', 'Are you sure you want to kick someone out of the game?',
                'Ya', 'Na'
            ))
        ]

        blocks = [
            PlainTextHeaderBlock('CAH Main Menu'),
            ActionsBlock(main_buttons),
            # BKitB.make_action_button_group(main_buttons),
            PlainTextSectionBlock('*Game Info*'),
            ActionsBlock(game_info_buttons),
            PlainTextSectionBlock('*Game Actions*'),
            ActionsBlock(game_action_buttons),
            PlainTextSectionBlock('*Player Info*'),
            ActionsBlock(player_info_buttons),
            PlainTextSectionBlock('*Player Actions*'),
            ActionsBlock(player_action_buttons),
        ]
        logger.debug('Sending menu form as private channel message.')
        self.st.private_channel_message(user_id=user, channel=channel,
                                        message='Welcome to the CAH Global Incorporated main menu!',
                                        blocks=blocks)

    @staticmethod
    def build_new_game_form_p1(decks: List[str]) -> BlocksType:
        """Builds a new game form with Block Kit"""
        decks_list = [(x, f'deck_{x}') for x in decks]
        return [StaticSelectSectionBlock('Select a deck :pickle-shy:', decks_list, placeholder='peek a deek',
                                         action_id='new-game-deck')]

    def build_new_game_form_p2(self) -> BlocksType:
        """Builds the second part to the new game form with Block Kit"""
        # Grab a query of 'active' players to serve as the initial users populated in the menu
        with self.eng.session_mgr() as session:
            active_players = [x.slack_user_hash for x in
                              session.query(TablePlayer).filter(TablePlayer.is_active).all()]
        logger.debug(f'Built out {len(active_players)} active players.')
        return [MultiUserSelectSectionBlock('Select the players', 'Pweese sewect some peopwe',
                                            action_id='new-game-users', initial_users=active_players)]

    @staticmethod
    def build_add_user_form() -> BlocksType:
        """Builds the second part to the new game form with Block Kit"""
        return [UserSelectSectionBlock('Select the player to add', placeholder='Player go here now',
                                       action_id='add-player-done')]

    @staticmethod
    def modify_question_form(original_value: str) -> BlocksType:
        """Builds the second part to the new game form with Block Kit"""
        return [
            PlainTextInputBlock('Make your change to the question below', action_id='modify-question',
                                initial_value=original_value),
            ActionsBlock([ButtonElement('Cancel', 'cancel', value='cancel', style='danger')]),
        ]

    @staticmethod
    def build_remove_user_form() -> BlocksType:
        """Builds the second part to the new game form with Block Kit"""
        return [UserSelectSectionBlock('Select the player to remove', 'Do it here!!!',
                                       action_id='remove-player-done')]

    @staticmethod
    def build_my_settings_form(eng: WizzyPSQLClient, user_id: str) -> BlocksType:
        """Builds a my details form"""
        # Lookup user
        player = eng.get_player_from_hash(user_hash=user_id)  # type: TablePlayer
        status_dict = {
            'arp': {
                'bool': player.is_auto_randpick,
                'value': 'toggle-auto-randpick'
            },
            'arc': {
                'bool': player.is_auto_randchoose,
                'value': 'toggle-auto-randchoose'
            },
            'arparca': {
                'bool': player.is_auto_randpick and player.is_auto_randchoose,
                'value': 'toggle-arparca'
            },
            'card dm': {
                'bool': player.is_dm_cards,
                'value': 'toggle-card-dm'
            }
        }
        buttons = []
        for k, v in status_dict.items():
            title = f'Turn {k.upper()} {"off" if v["bool"] else "on"}'
            buttons.append(
                ButtonElement(title, action_id=v['value'], value=v['value'], style='danger' if not v['bool'] else None)
            )

        honorific = f', {player.honorific}' if player.honorific is not None else ''
        with eng.session_mgr() as session:
            total_score = session.query(
                    func.sum(TablePlayerRound.score)
                ).filter(and_(
                    TablePlayerRound.player_key == player.player_id
                )).scalar()

            total_games_played = session.query(func.count(func.distinct(TablePlayerRound.game_key))).filter(
                    TablePlayerRound.player_key == player.player_id
                ).scalar()

            total_decknukes_issued = session.query(func.count(TablePlayerRound.is_nuked_hand)).filter(and_(
                    TablePlayerRound.player_key == player.player_id,
                    TablePlayerRound.is_nuked_hand
                )).scalar()

            total_decknukes_caught = session.query(func.count(TablePlayerRound.is_nuked_hand_caught)).filter(and_(
                    TablePlayerRound.player_key == player.player_id,
                    TablePlayerRound.is_nuked_hand_caught
                )).scalar()

            stats_dict = {
                'Overall score': total_score,
                'Games played': total_games_played,
                'Decknukes used': total_decknukes_issued,
                'Decknukes caught': total_decknukes_caught,
            }

        return [
            PlainTextHeaderBlock(f'Player details: {player.display_name.title()}{honorific}'),
            PlainTextSectionBlock([f'`{k:_<20}{v:_>5,}`' for k, v in stats_dict.items()]),
            ActionsBlock(buttons)
        ]
