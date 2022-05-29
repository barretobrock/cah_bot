"""
Cron endpoints that get hit with a cadence defined either in crontab or elsewhere.

Set URLs so they can be accessed
    0 * * * * /usr/bin/curl -X POST https://YOUR_APP/cron/ENDPOINT
"""
from datetime import datetime
from flask import (
    Blueprint,
)
from sqlalchemy.sql import (
    and_,
    null,
    or_
)
from cah.model import (
    GameStatus,
    TableTask
)
from cah.logg import get_base_logger
import cah.app as mainapp


cron = Blueprint('cron', __name__)
logg = get_base_logger()


@cron.route('/manager', methods=['POST'])
@logg.catch
def cron_manager():
    """Handles management of hitting endpoints regularly through the task table.
    This is generally hit the most frequently to determine whether any other endpoints need to be hit,
    but only based on certain conditions"""
    # Query tasks
    endpoints_to_call = []
    now = datetime.now()
    with mainapp.eng.session_mgr() as session:
        tasks = session.query(TableTask).filter(or_(
            null(TableTask.until_timestamp),
            TableTask.until_timestamp >= now
        )).all()
        if len(tasks) > 0:
            for task in tasks:
                task: TableTask
                if task.last_triggered is None:
                    # Add to endpoints to trigger
                    mainapp.logg.debug('Found task that has never been triggered. Adding to list')
                    endpoints_to_call.append(task.endpoint)
                diff = now - task.last_triggered


@cron.route('/handle-randpick', methods=['POST'])
@logg.catch
def handle_randpick():
    mainapp.logg.debug('Beginning randpick handling check...')
    if mainapp.Bot.current_game is not None:
        mainapp.Bot.current_game.handle_randpicks()


@cron.route('/handle-randchoose', methods=['POST'])
@logg.catch
def handle_randchoose():
    mainapp.logg.debug('Beginning randchoose handling check...')
    game = mainapp.Bot.current_game
    if game is not None and game.status == GameStatus.JUDGE_DECISION:
        if game.judge.is_arc and game.judge.selected_choice_idx is not None:
            mainapp.logg.info('Game is awaiting a choice from ARC\'d judge. Handling that now.')
            mainapp.Bot.choose_card(game.judge.player_hash, 'randchoose')


@cron.route('/force-choose', methods=['POST'])
@logg.catch
def force_choose():
    """Forces a choice on the judge, even if they aren't ARC"""
    mainapp.logg.debug('Forcing judge choice...')
    game = mainapp.Bot.current_game
    if game is not None and game.status == GameStatus.JUDGE_DECISION:
        if game.judge.selected_choice_idx is not None:
            mainapp.logg.info('Game is awaiting a choice from ARC\'d judge. Handling that now.')
            mainapp.Bot.choose_card(game.judge.player_hash, 'randchoose')
