"""
Cron endpoints that get hit with a cadence defined either in crontab or elsewhere.

Set URLs so they can be accessed
    0 * * * * /usr/bin/curl -X POST https://YOUR_APP/cron/ENDPOINT
"""
from datetime import datetime

from flask import (
    Blueprint,
    make_response,
)
from sqlalchemy.sql import or_

from cah.model import (
    GameStatus,
    TableTask,
    TableTaskParameter,
)
from cah.routes.helpers import (
    get_app_bot,
    get_app_logger,
    get_wizzy_eng,
)

bp_crons = Blueprint('crons', __name__, url_prefix='/api/crons')


@bp_crons.route('/manager', methods=['POST'])
def cron_manager():
    """Handles management of hitting endpoints regularly through the task table.
    This is generally hit the most frequently to determine whether any other endpoints need to be hit,
    but only based on certain conditions"""
    # Query tasks

    endpoints_to_call = []
    now = datetime.now()
    with get_wizzy_eng().session_mgr() as session:
        results = session.query(TableTask, TableTaskParameter) \
            .outerjoin(TableTaskParameter, TableTaskParameter.task_key == TableTask.task_id). \
            filter(or_(
                TableTask.until_timestamp.is_(None),
                TableTask.until_timestamp >= now
            )).all()
        if len(results) > 0:
            for task, parameters in results:
                task: TableTask
                if task.last_triggered is None:
                    # Add to endpoints to trigger
                    get_app_logger().debug('Found task that has never been triggered. Adding to list')
                    endpoints_to_call.append(task.endpoint)
                # diff = now - task.last_triggered
                # TODO: Make this into a list of dicts:
                #   task: [params]
    return make_response('', 200)


@bp_crons.route('/handle-randpick', methods=['POST'])
def handle_randpick():
    get_app_logger().debug('Beginning randpick handling check...')
    bot = get_app_bot()
    if bot.current_game is not None:
        bot.current_game.handle_randpicks()
    return make_response('', 200)


@bp_crons.route('/handle-randchoose', methods=['POST'])
def handle_randchoose():
    logg = get_app_logger()
    bot = get_app_bot()
    logg.debug('Beginning randchoose handling check...')
    game = bot.current_game
    if game is not None and game.status == GameStatus.JUDGE_DECISION:
        if game.judge.is_arc and game.judge.selected_choice_idx is not None:
            logg.info('Game is awaiting a choice from ARC\'d judge. Handling that now.')
            bot.choose_card(game.judge.player_hash, 'randchoose')
    return make_response('', 200)


@bp_crons.route('/force-choose', methods=['POST'])
def force_choose():
    """Forces a choice on the judge, even if they aren't ARC"""
    logg = get_app_logger()
    bot = get_app_bot()
    logg.debug('Forcing judge choice...')
    game = bot.current_game
    if game is not None and game.status == GameStatus.JUDGE_DECISION:
        if game.judge.selected_choice_idx is not None:
            logg.info('Game is awaiting a choice from ARC\'d judge. Handling that now.')
            bot.choose_card(game.judge.player_hash, 'randchoose')
    return make_response('', 200)
