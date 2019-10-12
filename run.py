#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from cah import CAHBot
from kavalkilu import Log, LogArgParser


# Initiate logging
log = Log('cah', log_lvl=LogArgParser().loglvl)

cbot = CAHBot(log)
try:
    cbot.run_rtm()
except KeyboardInterrupt:
    log.debug('Script ended manually.')
finally:
    cbot.message_grp('Shutdown for maintenance.:dotdotdot:')

log.close()



