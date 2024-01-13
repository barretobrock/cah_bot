from typing import Dict

from loguru import logger
from slacktools import SlackTools
from slacktools.api.web.users import UserInfo

from cah.db_eng import WizzyPSQLClient
from cah.model import TablePlayer


def process_player_slack_details(uid: str, user_info: UserInfo) -> Dict[str, str]:
    """This handles processing incoming slack details for a single user"""
    display_name = user_info.profile.display_name
    real_name = user_info.real_name
    display_name = real_name if display_name == '' else display_name
    return {
        'slack_user_hash': uid,
        'display_name': display_name,
        'avi_url': user_info.profile.image_32
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
    user_info: UserInfo
    for user_info in channel_users:
        uid = user_info.id
        log.debug(f'Working on {user_info.real_name}')
        params = process_player_slack_details(uid=uid, user_info=user_info)
        if uid in current_uids:
            with eng.session_mgr() as session:
                # Get player
                session.query(TablePlayer).filter(TablePlayer.slack_user_hash == uid).\
                    update({
                        TablePlayer.display_name: params.get('display_name'),
                        TablePlayer.avi_url: params.get('avi_url')
                    })
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
        active_player_hashes = [x.id for x in channel_users]
        eng.set_active_players(player_hashes=active_player_hashes)
