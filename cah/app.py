import json
import requests
import signal
import sqlite3
from random import choice
from flask import Flask, request, make_response
from slacktools import SlackEventAdapter, SecretStore
from easylogger import Log
import cah.bot_base as botbase
from .settings import auto_config


bot_name = 'wizzy'
logg = Log(bot_name, log_to_file=True)
# This is basically a session maker. We'll use it to ensure that sessions stay independent and short-lived
#   while also not having them become an encumbrance to the state of the code
Session = auto_config.SESSION

credstore = SecretStore('secretprops-bobdev.kdbx')
cah_creds = credstore.get_key_and_make_ns(bot_name)

logg.debug('Instantiating bot...')
Bot = botbase.CAHBot(parent_log=logg, session=Session())

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
    # if channel empty, it's a shortcut
    if event_data.get('channel') is None:
        # shortcut - grab callback, put in action dict according to expected ac
        action = {
            'action_id': event_data.get('callback_id'),
            'action_value': '',
            'type': 'shortcut'
        }
        channel = auto_config.MAIN_CHANNEL
    else:
        # Action from button click, etc...
        channel = event_data['channel']['id']
        actions = event_data['actions']
        # Not sure if we'll ever receive more than one action?
        action = actions[0]
    # Send that info onwards to determine how to deal with it
    Bot.process_incoming_action(user, channel, action_dict=action, event_dict=event_data, session=Session())

    # Respond to the initial message and update it
    responses = [
        'Thanks, shithead!',
        'Good job, you did a thing!',
        'Look at you, doing things and shit!',
        'Hey, you\'re a real pal!',
        'Thanks, I guess...'
    ]
    update_dict = {
        'replace_original': True,
        'text': choice(responses)
    }
    if event_data.get('container', {'is_ephemeral': False}).get('is_ephemeral', False):
        update_dict['response_type'] = 'ephemeral'
    response_url = event_data.get('response_url')
    if response_url is not None:
        # Update original message
        resp = requests.post(event_data['response_url'], json=update_dict,
                             headers={'Content-Type': 'application/json'})

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)


@bot_events.on('message')
def scan_message(event_data):
    session = Session()
    try:
        Bot.process_event(event_data, session=session)
    except sqlite3.ProgrammingError:
        session.rollback()


@app.route('/api/slash', methods=['GET', 'POST'])
def handle_slash():
    """Handles a slash command"""
    event_data = request.form
    # Handle the command
    Bot.process_slash_command(event_data, Session())

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)
