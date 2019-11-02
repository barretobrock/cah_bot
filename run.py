#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import cah
from datetime import datetime as dt
from kavalkilu import Log, LogArgParser


# Initiate logging
log = Log('cah', log_lvl=LogArgParser().loglvl)

cbot = cah.CAHBot(log)
try:
    info_dict = {
        'bot': 'CAH bot',
        'version': cah.__version__,
        'update': dt.strptime(cah.__update_date__, '%Y-%m-%dT%H:%M:%S%z'),
        'msg': 'Booted up and ready to play!'
    }
    bootup_msg = '```{bot:-^50}\n{version:>20} updated {update:%F %T}\n{msg:-^50}```'.format(**info_dict)
    kill_msg = 'Daemon killed, but gracefully. :party-dead:'
    cbot.run_rtm(bootup_msg, kill_msg)
except KeyboardInterrupt:
    log.debug('Script ended manually.')
finally:
    cbot.message_grp('Shutdown for maintenance.:dotdotdot:')

log.close()



