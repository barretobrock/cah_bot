import json
import os
import re

from flask import (
    Blueprint,
    current_app,
    make_response,
    request,
)
import requests
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from cah.routes.helpers import get_app_bot
from cah.settings import (
    Development,
    Production,
)

bp_actions = Blueprint('actions', __name__)

ENV = os.getenv('CAH_ENV')
if ENV is None:
    raise ValueError('No set env. Cannot proceed')
if ENV == 'DEV':
    env_class = Development
else:
    env_class = Production

env_class.load_secrets()
props = env_class.SECRETS
bolt_app = App(token=props['xoxb-token'], signing_secret=props['signing-secret'], process_before_response=True)
handler = SlackRequestHandler(app=bolt_app)


@bp_actions.route('/api/actions', methods=['GET', 'POST'])
def handle_event():
    """Handles a slack event"""
    return handler.handle(req=request)


@bolt_app.action(re.compile('.*'))
def handle_action(ack):
    """Handle a response when a user clicks a button from Wizzy in Slack"""
    ack()
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
    if event_data.get('container', {'is_ephemeral': False}).get('is_ephemeral', False):
        update_dict['response_type'] = 'ephemeral'
    response_url = event_data.get('response_url')
    if response_url is not None:
        # Update original message
        if 'shortcut' not in action.get('type'):
            _ = requests.post(event_data['response_url'], json=update_dict,
                              headers={'Content-Type': 'application/json'})

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)
