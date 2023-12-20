from typing import TYPE_CHECKING

from flask import (
    Blueprint,
    current_app,
    request,
)
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from cah.routes.helpers import (
    get_app_bot,
    get_app_logger,
    get_wizzy_eng,
)
from cah.settings import Development

if TYPE_CHECKING:
    from cah.model import TablePlayer

bp_events = Blueprint('events', __name__)


Development.load_secrets()
props = Development.SECRETS
bolt_app = App(token=props['xoxb-token'], signing_secret=props['signing-secret'], process_before_response=True)
handler = SlackRequestHandler(app=bolt_app)


@bp_events.route('/api/events', methods=['GET', 'POST'])
def handle_event():
    """Handles a slack event"""
    return handler.handle(req=request)


@bolt_app.event('message')
def scan_message(ack):
    ack()
    event_data = request.json
    get_app_bot().process_event(event_data)


@bolt_app.event('user_change')
def notify_new_statuses(event_data):
    """Triggered when a user updates their profile info. Gets saved to global dict
    where we then report it in #general"""
    logg = get_app_logger()
    eng = get_wizzy_eng()

    event = event_data['event']
    user_info = event['user']
    uid = user_info['id']

    # Look up user in db
    user_obj = eng.get_player_from_hash(user_hash=uid)  # type: TablePlayer
    logg.debug(f'User change detected for {uid}')
    if user_obj is None:
        logg.warning(f'Couldn\'t find user: {uid} \n {user_info}')
        return

    # get display name
    profile = user_info.get('profile')
    display_name = profile.get('display_name')
    if any([
        # Maybe some other attributes?
        user_obj.display_name != display_name,
    ]):
        # Update the user
        with eng.session_mgr() as session:
            session.add(user_obj)
            user_obj.display_name = display_name
        logg.debug(f'User {display_name} updated in db.')
