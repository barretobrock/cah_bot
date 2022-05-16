import random
from typing import (
    Dict,
    List,
    Tuple
)
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


def mock_get_score(n_players: int = 10) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Mocks the return for the queries in get_score"""
    players = []
    for p in range(n_players):
        player = make_player()
        player.player_id = p + 1
        players.append(player)
    mock_overall = [
        {
            'player_id': x.player_id,
            'display_name': x.display_name,
            'overall': random.randint(0, 30)
        } for x in players
    ]

    mock_current = []
    for x in mock_overall:
        x = x.copy()
        # Add in the overall score, but randomly subtract some points from it to better imitate real conditions
        x['current'] = x.pop('overall') - random.randint(1, 10)
        mock_current.append(x)

    mock_previous = []
    # Pick a random player & subtract their score by one. They were last round's winner.
    rand_pos = random.randint(0, len(mock_current))
    for i, x in enumerate(mock_current.copy()):
        x = x.copy()
        x['prev_round'] = x.pop('current')
        if i == rand_pos:
            x['prev_round'] -= 1
        mock_previous.append(x)

    return mock_overall, mock_current, mock_previous
