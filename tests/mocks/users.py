from random import choice
from string import (
    ascii_uppercase,
    printable
)


def random_user(is_bot: bool = False) -> str:
    """Generates a random user id"""
    prefix = 'B' if is_bot else 'U'
    user = ''.join(choice(ascii_uppercase) for _ in range(10))
    return f'{prefix}{user}'


def random_display_name() -> str:
    """Generates a random user display_name"""
    return ''.join(choice(printable) for _ in range(30))
