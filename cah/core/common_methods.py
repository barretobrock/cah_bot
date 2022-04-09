from typing import Dict
from loguru import logger
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
        'avi_url': profile_dict.get('avi32')
    }


def refresh_players_in_channel(channel: str, eng: WizzyPSQLClient, st: SlackTools, log: logger,
                               check_activity: bool = False):
    """Confirms the players in the channel, adds new ones and flags ones that aren't present"""
    log.debug('Fetching players in table')
    with eng.session_mgr() as session:
        current_uids = [x.slack_user_hash for x in session.query(TablePlayer).all()]
    log.debug(f'{len(current_uids)} found existing.')
    log.debug('Getting users in #general')
    channel_users = st.get_channel_members(channel=channel, humans_only=True)
    usr_tbls = []
    # First, we scan all active users in channel for changes
    for user_dict in channel_users:
        uid = user_dict['id']
        log.debug(f'Working on {uid}')
        params = process_player_slack_details(uid=uid, profile_dict=user_dict)
        if uid in current_uids:
            with eng.session_mgr() as session:
                # Get player
                player = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == uid).one()
                player.display_name = params.get('display_name')
                player.avi_url = params.get('avi_url')
                eng.refresh_table_object(tbl_obj=player, session=session)
        else:
            usr_tbls.append(
                TablePlayer(**params)
            )
    log.debug(f'Found {len(usr_tbls)} new users to add to table.')
    if len(usr_tbls) > 0:
        with eng.session_mgr() as session:
            session.add_all(usr_tbls)

    if check_activity:
        # Then, we process users in the channel for activity
        log.debug('Setting users as active if they\'re members of the channel')
        active_player_hashes = [x['id'] for x in channel_users]
        eng.set_active_players(player_hashes=active_player_hashes)
