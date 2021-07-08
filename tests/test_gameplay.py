from slacktools import SecretStore
from easylogger import Log
import cah.app as cahapp
from cah.settings import auto_config


bot_name = auto_config.BOT_NICKNAME
logg = Log(bot_name, log_to_file=True)

credstore = SecretStore('secretprops-bobdev.kdbx')
cah_creds = credstore.get_key_and_make_ns(bot_name)


def collect_outgoing(*args, **kwargs):
    if args is None:
        return
    logg.debug(f'outgoing msg')


logg.debug('Instantiating bot...')
Bot = cahapp.Bot
sesh = cahapp.db.session
# Patch outgoing messages while testing
original_send = Bot.st.send_message
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
Bot.new_game(deck='standard', player_ids=[x.player_id for x in players[:-1]])

for nth_round in range(40):
    # Judge has to make a pick, bc the sequence is built to take in at least one input from a user
    Bot.ping_players_left_to_pick()
    if nth_round == 0:
        # Test status output
        # Bot.st.send_message = original_send
        # blocks = Bot.display_status()
        # Bot.st.send_message(channel=auto_config.MAIN_CHANNEL, message='this is a test',
        #                     blocks=blocks)
        #
        # Bot.st.send_message = collect_outgoing
        pass
    elif nth_round == 5:
        # 5th round, someone decides to decknuke every round after that
        Bot.game.players.player_list[0].toggle_arp()
    elif nth_round == 10:
        # add player to game
        Bot.game.players.add_player_to_game(players[-1].player_id, game_id=Bot.game.game_tbl.id,
                                            round_id=Bot.game.gameround.id)
    elif nth_round == 20:
        # add player to game
        Bot.game.players.remove_player_from_game(players[-1].player_id)
    if 10 < nth_round < 30:
        Bot.choose_card(Bot.game.judge.player_id, 'randchoose 234')
    else:
        Bot.choose_card(Bot.game.judge.player_id, 'choose 1')
    if Bot.game.status.name == 'players_decision':
        Bot.decknuke(Bot.game.players.player_list[0].player_id)
Bot.display_status()
Bot.display_points()
Bot.end_game()
logg.debug('Complete!')
