import os
import json
import traceback
import requests
import signal
from flask import Flask, request, make_response
from slacktools import SlackEventAdapter
from .utils import CAHBot


bot_name = 'cah'
DEBUG = os.environ['CAH_DEBUG'] == '1'

key_path = os.path.join(os.path.expanduser('~'), 'keys')
key_dict = {}
for t in ['SIGNING_SECRET', 'XOXB_TOKEN', 'XOXP_TOKEN', 'VERIFY_TOKEN']:
    with open(os.path.join(key_path, f'{bot_name.upper()}_SLACK_{t}')) as f:
        key_dict[t.lower()] = f.read().strip()

Bot = CAHBot(bot_name, key_dict['xoxb_token'], key_dict['xoxp_token'], debug=DEBUG)
# Register the cleanup function as a signal handler
signal.signal(signal.SIGINT, Bot.cleanup)
signal.signal(signal.SIGTERM, Bot.cleanup)
message_events = []
app = Flask(__name__)


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


# Events API listener
bot_events = SlackEventAdapter(key_dict['signing_secret'], "/cah/cahapi/events", app)


@bot_events.on('message')
def scan_message(event_data):
    event = event_data['event']
    # Pass event stuff onward to app
    msg_packet = None
    if event['type'] == 'message' and "subtype" not in event:
        trigger, message, raw_message = Bot.st.parse_direct_mention(event['text'])
        if trigger in Bot.triggers:
            # Build a message hash
            msg_hash = f'{event["channel"]}_{event["ts"]}'
            if msg_hash not in message_events:
                message_events.append(msg_hash)
                msg_packet = {
                    'message': message.strip(),
                    'raw_message': raw_message.strip()
                }
                # Add in all the other stuff
                msg_packet.update(event)

    if msg_packet is not None:
        try:
            Bot.st.handle_command(msg_packet)
        except Exception as e:
            if not isinstance(e, RuntimeError):
                exception_msg = '{}: {}'.format(e.__class__.__name__, e)
                if Bot.debug:
                    blocks = [
                        Bot.bkb.make_context_section("Exception occurred: \n```{}```".format(exception_msg)),
                        Bot.bkb.make_block_divider(),
                        Bot.bkb.make_context_section(f'```{traceback.format_exc()}```')
                    ]
                    Bot.st.send_message(msg_packet['channel'], message='', blocks=blocks)
                else:
                    Bot.st.send_message(msg_packet['channel'], f"Exception occurred: \n```{exception_msg}```")


