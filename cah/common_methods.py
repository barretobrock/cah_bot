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
        'display_name': display_name
    }


def refresh_players_in_channel(eng: WizzyPSQLClient, st: SlackTools, log: Log):
    """Confirms the players in the channel, adds new ones and flags ones that aren't present"""
    channel = 'CMEND3W3H'  # General channel to get all possible players
    log.debug('Fetching players in table')
    with eng.session_mgr() as session:
        current_uids = [x.slack_user_hash for x in session.query(TablePlayer).all()]

    users = st.get_channel_members(channel=channel, humans_only=True)
    usr_tbls = []
    for user_dict in users:
        uid = user_dict['id']
        if uid in current_uids:
            continue

        params = process_player_slack_details(uid=uid, profile_dict=user_dict)
        usr_tbls.append(
            TablePlayer(**params)
        )
    log.debug(f'Found {len(usr_tbls)} users to add to table.')
    if len(usr_tbls) > 0:
        with eng.session_mgr() as session:
            session.add_all(usr_tbls)
