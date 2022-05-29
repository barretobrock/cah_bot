import json
import signal
import requests
from flask import (
    Flask,
    request,
    make_response
)
from slackeventsapi import SlackEventAdapter
from slacktools import SecretStore
from cah.model import TablePlayer
from cah.db_eng import WizzyPSQLClient
from cah.settings import auto_config
from cah.logg import get_base_logger
from cah.bot_base import CAHBot
from cah.crons import cron

# TODO:
#  - add menu to control other users that are unresponsive (e.g., arparca)
#  - split out the main menu into general and in-game commands
#       - in-game commands given priority when a game is active, otherwise general commands are priority.
#           (this will require adding an overflow element to the menu)

bot_name = auto_config.BOT_NICKNAME
logg = get_base_logger()

credstore = SecretStore('secretprops-davaiops.kdbx')
# Set up database connection
conn_dict = credstore.get_entry(f'davaidb-{auto_config.ENV.lower()}').custom_properties
cah_creds = credstore.get_key_and_make_ns(bot_name)

logg.debug('Starting up app...')
app = Flask(__name__)
app.register_blueprint(cron, url_prefix='/cron')

logg.debug('Initializing db engine...')
eng = WizzyPSQLClient(props=conn_dict, parent_log=logg)

logg.debug('Instantiating bot...')
Bot = CAHBot(eng=eng, bot_cred_entry=cah_creds, parent_log=logg)

# Register the cleanup function as a signal handler
signal.signal(signal.SIGINT, Bot.cleanup)
signal.signal(signal.SIGTERM, Bot.cleanup)

# Events API listener
bot_events = SlackEventAdapter(cah_creds.signing_secret, "/api/events", app)


@app.route('/api/actions', methods=['GET', 'POST'])
@logg.catch
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
    Bot.process_incoming_action(user, channel, action_dict=action, event_dict=event_data)

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


@bot_events.on('message')
@logg.catch
def scan_message(event_data):
    Bot.process_event(event_data)


@app.route('/api/slash', methods=['GET', 'POST'])
@logg.catch
def handle_slash():
    """Handles a slash command"""
    event_data = request.form
    # Handle the command
    Bot.process_slash_command(event_data)

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)


@bot_events.on('user_change')
@logg.catch
def notify_new_statuses(event_data):
    """Triggered when a user updates their profile info. Gets saved to global dict
    where we then report it in #general"""
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
