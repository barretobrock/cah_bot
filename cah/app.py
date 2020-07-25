import os
import json
import requests
import signal
from flask import Flask, request, make_response
from slacktools import SlackEventAdapter
from kavalkilu import Path, Log
from .utils import CAHBot


bot_name = 'cah'
DEBUG = os.environ['CAH_DEBUG'] == '1'
kpath = Path()
logg = Log(bot_name)

key_path = kpath.easy_joiner(kpath.keys_dir, f'{bot_name.upper()}_SLACK_KEYS.json')
with open(key_path) as f:
    key_dict = json.loads(f.read())
logg.debug('Instantiating bot...')
Bot = CAHBot(bot_name, creds=key_dict, debug=DEBUG)

# Register the cleanup function as a signal handler
signal.signal(signal.SIGINT, Bot.cleanup)
signal.signal(signal.SIGTERM, Bot.cleanup)
message_events = []
app = Flask(__name__)

# Events API listener
bot_events = SlackEventAdapter(key_dict['signing_secret'], "/cah/cahapi/events", app)


@app.route('/cah/cahapi/actions', methods=['GET', 'POST'])
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
