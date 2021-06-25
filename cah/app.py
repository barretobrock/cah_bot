import os
import json
import requests
import signal
from random import choice
from flask import Flask, request, make_response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from slacktools import SlackEventAdapter, SecretStore
from easylogger import Log
import cah.bot_base as botbase
from .settings import auto_config
from .model import Base


bot_name = 'wizzy'
logg = Log(bot_name, log_to_file=True)

# Load database
db_path = os.path.join(os.path.expanduser('~'), *['data', 'cah_db.db'])
engine = create_engine(f'sqlite:///{db_path}')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

credstore = SecretStore('secretprops-bobdev.kdbx')
cah_creds = credstore.get_key_and_make_ns(bot_name)

logg.debug('Instantiating bot...')
Bot = botbase.CAHBot(parent_log=logg)

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
    Bot.process_incoming_action(user, channel, action, event_dict=event_data)

    # Respond to the initial message and update it
    responses = [
        'Thanks, shithead!', 'Good job, you did a thing!', 'Look at you, doing things and shit!',
        'Hey, you\'re a real pal!', 'Thanks, I guess...'
    ]
    update_dict = {
        'replace_original': True,
        'text': choice(responses)
    }
    if event_data.get('container', {'is_ephemeral': False}).get('is_ephemeral', False):
        update_dict['response_type'] = 'ephemeral'
    resp = requests.post(event_data['response_url'], json=update_dict,
                         headers={'Content-Type': 'application/json'})

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)


@bot_events.on('message')
def scan_message(event_data):
    Bot.st.parse_event(event_data)
