import json

from flask import (
    Blueprint,
    current_app,
    make_response,
    request,
)
import requests

from cah.routes.helpers import get_app_bot

bp_actions = Blueprint('actions', __name__)


@bp_actions.route('/api/actions', methods=['GET', 'POST'])
def handle_action():
    """Handle a response when a user clicks a button from Wizzy in Slack"""
    event_data = json.loads(request.form["payload"])
    user = event_data['user']['id']
    # if channel empty, it's a shortcut
    if event_data.get('channel') is None:
        # shortcut - grab callback, put in action dict according to expected ac
        action = {
            'action_id': event_data.get('callback_id'),
            'action_value': '',
            'type': 'shortcut'
        }
        channel = current_app.config.get('MAIN_CHANNEL')
    else:
        # Action from button click, etc...
        channel = event_data['channel']['id']
        actions = event_data['actions']
        # Not sure if we'll ever receive more than one action?
        action = actions[0]
    # Send that info onwards to determine how to deal with it
    get_app_bot().process_incoming_action(user, channel, action_dict=action, event_dict=event_data)

    # Respond to the initial message and update it
    update_dict = {
        'delete_original': True
    }
    response_url = event_data.get('response_url')
    if response_url is not None:
        # Update original message
        _ = requests.post(event_data['response_url'], json=update_dict,
                          headers={'Content-Type': 'application/json'})

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)
