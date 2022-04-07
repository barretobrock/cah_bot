from typing import Dict
from easylogger import Log
from slacktools import SlackTools
from cah.model import TablePlayer
from cah.db_eng import WizzyPSQLClient


def process_player_slack_details(uid: str, profile_dict: Dict) -> Dict[str, str]:
    """This handles processing incoming slack details for a single user"""
    display_name = profile_dict.get('display_name', '')
    real_name = profile_dict.get('real_name', 'wtfevenisyourname')
    display_name = real_name if display_name == '' else display_name
    return {
        'slack_user_hash': uid,
        'display_name': display_name,
        'avi_url': profile_dict.get('avi')
    }


def refresh_players_in_channel(eng: WizzyPSQLClient, st: SlackTools, log: Log):
    """Confirms the players in the channel, adds new ones and flags ones that aren't present"""
    channel = 'CMEND3W3H'  # General channel to get all possible players
    log.debug('Fetching players in table')
    with eng.session_mgr() as session:
        current_uids = [x.slack_user_hash for x in session.query(TablePlayer).all()]
    log.debug(f'{len(current_uids)} found existing.')
    log.debug('Getting users in #general')
    users = st.get_channel_members(channel=channel, humans_only=True)
    usr_tbls = []
    for user_dict in users:
        uid = user_dict['id']
        log.debug(f'Working on {uid}')
        params = process_player_slack_details(uid=uid, profile_dict=user_dict)
        if uid in current_uids:
            with eng.session_mgr() as session:
                # Get player
                player = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == uid).one()
                player.display_name = params.get('display_name')
                player.avi_url = params.get('avi_url')
                session.add(player)
        else:
            usr_tbls.append(
                TablePlayer(**params)
            )
    log.debug(f'Found {len(usr_tbls)} new users to add to table.')
    if len(usr_tbls) > 0:
        with eng.session_mgr() as session:
            session.add_all(usr_tbls)
