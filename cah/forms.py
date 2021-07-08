from typing import List, Dict
from sqlalchemy.orm import Session
from slacktools import BlockKitBuilder as bkb, SlackTools
from .model import GameStatuses, TablePlayers
from .games import Game


class Forms:
    """Stores various Block Kit forms"""

    @classmethod
    def build_main_menu(cls, game_obj: Game, slack_api: SlackTools, user: str, channel: str):
        """Generates and sends a main menu"""
        button_list = []
        if game_obj is None:
            # No game started, put the new game button at the beginning.
            button_list.append(
                bkb.make_action_button('New Game', value='newgame', action_id='new-game-start', danger_style=False)
            )
        button_list += [
            bkb.make_action_button('Status', value='status', action_id='status'),
            bkb.make_action_button('Scores', value='score', action_id='score'),
            bkb.make_action_button('My Settings', value='my-settings', action_id='my-settings'),
            bkb.make_action_button('Add', value='add-player', action_id='add-player'),
            bkb.make_action_button('Kick', value='remove-player', action_id='remove-player'),
        ]
        if game_obj is not None and game_obj.status not in [GameStatuses.ended]:
            button_list.append(
                bkb.make_action_button('End Game', value='end-game', action_id='end-game', danger_style=True,
                                       incl_confirm=True, confirm_title='Really end game?',
                                       confirm_text='Are you sure you want to end the game?', ok_text='Ya',
                                       deny_text='Na')
            )
        blocks = [
            bkb.make_header('CAH International Main Menu'),
            bkb.make_action_button_group(button_list)
        ]
        slack_api.private_channel_message(user_id=user, channel=channel,
                                          message='Welcome to the CAH Global Incorporated main menu!',
                                          blocks=blocks)

    @staticmethod
    def build_new_game_form_p1(decks: List['Deck']) -> List[Dict]:
        """Builds a new game form with Block Kit"""
        decks_list = [{'txt': x, 'value': f'deck_{x}'} for x in decks]

        return [bkb.make_static_select('Select a deck', option_list=decks_list, action_id='new-game-deck')]

    @staticmethod
    def build_new_game_form_p2(user_id: str) -> List[Dict]:
        """Builds the second part to the new game form with Block Kit"""
        return [bkb.make_multi_user_select('Select the players', initial_users=[user_id],
                                           action_id='new-game-users')]

    @staticmethod
    def build_add_user_form() -> List[Dict]:
        """Builds the second part to the new game form with Block Kit"""
        return [bkb.make_user_select('Select the player to add', action_id='add-player-done')]

    @staticmethod
    def build_remove_user_form() -> List[Dict]:
        """Builds the second part to the new game form with Block Kit"""
        return [bkb.make_user_select('Select the player to remove', action_id='remove-player-done')]

    @staticmethod
    def build_my_settings_form(session_object: Session, user_id: str) -> List[Dict]:
        """Builds a my details form"""
        # Lookup user
        player = session_object.query(TablePlayers)\
            .filter(TablePlayers.slack_id == user_id).one_or_none()  # type: TablePlayers
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
            buttons.append(bkb.make_action_button(title, value=v['value'], action_id=v['value'],
                                                  danger_style=not v['bool']))

        honorific = f', {player.honorific}' if player.honorific is not None else ''
        stats_dict = {
            'Overall score': player.total_score,
            'Games played': player.total_games_played,
            'Decknukes used': player.total_decknukes_issued,
            'Decknukes caught': player.total_decknukes_caught,
        }

        return [
            bkb.make_header(f'Player details: {player.name.title()}{honorific}'),
            bkb.make_block_section([f'`{k:_<20}{v:_>5,}`' for k, v in stats_dict.items()])
        ] + [bkb.make_action_button_group([x]) for x in buttons]
