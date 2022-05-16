from cah.model import (
    TablePlayer,
    TablePlayerRound
)
from .users import (
    random_display_name,
    random_user
)


def make_player(dm_cards: bool = True, arp: bool = False, arc: bool = False, active: bool = True) -> TablePlayer:
    """Makes a random player"""
    return TablePlayer(
        slack_user_hash=random_user(),
        display_name=random_display_name(),
        avi_url='',
        honorific='',
        is_dm_cards=dm_cards,
        is_auto_randpick=arp,
        is_auto_randchoose=arc,
        is_active=active
    )


def get_overall_score(n_players: int = 10):
    """Gets the overall score for players"""
    players = [make_player() for _ in range(n_players)]



