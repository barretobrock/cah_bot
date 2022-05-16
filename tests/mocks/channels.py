from random import choice
from string import ascii_uppercase


def random_channel() -> str:
    """Generates a random user id"""
    channel = ''.join(choice(ascii_uppercase) for _ in range(10))
    return f'C{channel}'
