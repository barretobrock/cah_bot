import os
import json
import requests
import signal
from typing import Dict
from flask import Flask, request, make_response
from slacktools import SlackEventAdapter, SecretStore
from easylogger import Log
from kavalkilu import Path
from .utils import CAHBot


bot_name = 'wizzy'
DEBUG = os.environ['CAH_DEBUG'] == '1'
kpath = Path()
logg = Log(bot_name)


def read_props() -> Dict[str, str]:
    props = {}
    with open(os.path.abspath('./secretprops.properties'), 'r') as f:
        contents = f.read().split('\n')
        for item in contents:
            key, value = item.split('=', 1)
            props[key] = value.strip()
    return props


secretprops = read_props()
credstore = SecretStore('secretprops-bobdev.kdbx', secretprops['slacktools_secret'])
cah_creds = credstore.get_key_and_make_ns(bot_name)

logg.debug('Instantiating bot...')
Bot = CAHBot(bot_name, credstore=credstore, debug=DEBUG)

# Register the cleanup function as a signal handler
signal.signal(signal.SIGINT, Bot.cleanup)
signal.signal(signal.SIGTERM, Bot.cleanup)
message_events = []
app = Flask(__name__)

# Events API listener
bot_events = SlackEventAdapter(cah_creds.signing_secret, "/api/events", app)


@app.route('/api/actions', methods=['GET', 'POST'])
def handle_action():
    """Handle a response when a user clicks a button from Wizzy in Slack"""
    event_data = json.loads(request.form["payload"])
    user = event_data['user']['id']
    channel = event_data['channel']['id']
    actions = event_data['actions']
    # Not sure if we'll ever receive more than one action?
    action = actions[0]
    # Send that info onwards to determine how to deal with it
    Bot.process_incoming_action(user, channel, action)

    # Respond to the initial message and update it
    update_dict = {
        'replace_original': True,
        'text': 'Thanks, shithead!'
    }
    if event_data['container']['is_ephemeral']:
        update_dict['response_type'] = 'ephemeral'
    resp = requests.post(event_data['response_url'], json=update_dict,
                         headers={'Content-Type': 'application/json'})

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)


@bot_events.on('message')
def scan_message(event_data):
    Bot.st.parse_event(event_data)
