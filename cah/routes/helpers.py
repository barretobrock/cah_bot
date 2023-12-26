import time

from flask import (
    current_app,
    g,
    request,
)
from pukr import PukrLog


def get_db_conn():
    return current_app.config['db']


def get_session():
    return get_db_conn().session


def get_wizzy_eng():
    return current_app.config['eng']


def get_app_logger() -> PukrLog:
    return current_app.extensions['logg']


def get_app_bot():
    return current_app.extensions['bot']


def log_before():
    g.start_time = time.perf_counter()


def log_after(response):
    total_time = time.perf_counter() - g.start_time
    time_ms = int(total_time * 1000)
    get_app_logger().info(f'Timing: {time_ms}ms [{request.method}] -> {request.path}')
    return response
