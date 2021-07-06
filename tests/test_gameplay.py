from slacktools import SecretStore
from easylogger import Log
import cah.app as cahapp
from cah.settings import auto_config


bot_name = auto_config.BOT_NICKNAME
logg = Log(bot_name, log_to_file=True)
# This is basically a session maker. We'll use it to ensure that sessions stay independent and short-lived
#   while also not having them become an encumbrance to the state of the code
Session = auto_config.SESSION

credstore = SecretStore('secretprops-bobdev.kdbx')
cah_creds = credstore.get_key_and_make_ns(bot_name)


def collect_outgoing(*args, **kwargs):
    if args is None:
        return
    arguments = ' '.join([str(x) for x in args])
    logg.debug(f'outgoing msg:\nargs={arguments}\nkwargs={kwargs}')


logg.debug('Instantiating bot...')
sesh = Session()
Bot = cahapp.Bot
# Patch outgoing messages while testing
Bot.st.send_message = collect_outgoing
Bot.st.private_channel_message = collect_outgoing
Bot.st.private_message = collect_outgoing
Bot.st.update_message = collect_outgoing
Bot.st.delete_message = collect_outgoing

players = Bot.potential_players.player_list
# Switch channel back to standard game channel
for player in players:
    if player.player_table.is_dm_cards:
        player.toggle_cards_dm()
    if not player.player_table.is_auto_randpick:
        player.toggle_arp()
    if not player.player_table.is_auto_randchoose:
        player.toggle_arc()
if Bot.global_game_settings_tbl.is_ping_winner:
    Bot.toggle_winner_ping()
if Bot.global_game_settings_tbl.is_ping_judge:
    Bot.toggle_judge_ping()
Bot.new_game(deck='standard', player_ids=[x.player_id for x in players])

for nth_round in range(30):
    # Judge has to make a pick, bc the sequence is built to take in at least one input from a user
    if nth_round == 5:
        # 5th round, someone decides to decknuke every round after that
        Bot.game.players.player_list[0].toggle_arp()
    Bot.choose_card(Bot.game.judge.player_id, 'choose 1')
    if Bot.game.status.name == 'players_decision':
        Bot.decknuke(Bot.game.players.player_list[0].player_id)
    logg.debug(f'round {nth_round}....')
logg.debug('Complete!')
