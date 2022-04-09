import sys
from pathlib import Path
from loguru import logger


SERVICE_NAME = 'cah'


def get_base_logger() -> logger:
    """Return the logger object that serves as the base logger"""
    LOGPATH = Path().home().joinpath('logs').joinpath(SERVICE_NAME)
    # Make the directory path if it doesn't exist
    LOGPATH.mkdir(parents=True, exist_ok=True)
    FORMAT = '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | ' \
             '<cyan>{name} -> {extra[child_name]}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - ' \
             '<level>{message}</level>'
    config = {
        'handlers': [
            {'sink': sys.stdout, 'level': 'DEBUG', 'format': FORMAT},
            {'sink': LOGPATH.joinpath(f'{SERVICE_NAME}.log'), 'level': 'DEBUG', 'rotation': '1 day',
             'retention': '30 days', 'format': FORMAT, 'enqueue': True}
        ],
        'extra': {'child_name': 'main'}
    }
    logger.configure(**config)
    return logger
