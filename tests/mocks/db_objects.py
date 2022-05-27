import random
from typing import (
    Dict,
    List,
    Tuple
)
from datetime import datetime
import pandas as pd
import numpy as np
from cah.model import (
    GameStatus,
    TableGame,
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


def mock_game_tbl(game_id: int = None, deck_key: int = None, status: GameStatus = None, end_time: datetime = None):
    return TableGame(
        game_id=game_id if game_id is not None else random.randint(1, 50),
        deck_key=deck_key if deck_key is not None else random.randint(1, 12),
        status=status if status is not None else GameStatus.INITIATED,
        end_time=end_time
    )


def mock_get_score(n_players: int = 10, lims_overall: Tuple[int, int] = (0, 30),
                   lims_current: Tuple[int, int] = (0, 10)) -> Tuple[List[Dict], List[Dict], List[Dict]]:
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
            'overall': random.randint(*lims_overall)
        } for x in players
    ]

    mock_current = []
    for x in mock_overall:
        x = x.copy()
        # Add in the overall score, but randomly subtract some points from it to better imitate real conditions
        _ = x.pop('overall')
        x['current'] = random.randint(*lims_current)
        mock_current.append(x)

    mock_previous = []
    # Pick a random player & subtract their score by one. They were last round's winner.
    rand_pos = random.randint(0, len(mock_current))
    for i, x in enumerate(mock_current.copy()):
        x = x.copy()
        x['prev'] = x.pop('current')
        if i == rand_pos:
            x['prev'] -= 1
        mock_previous.append(x)

    return mock_overall, mock_current, mock_previous


def mock_get_rounds_df(n_rounds: int = 10, n_players: int = 10) -> pd.DataFrame:
    """Returns a dataframe of the previous rounds"""
    start_round = 12
    player_ids = random.sample(range(1, 20), n_players)
    winner_id = random.choice(player_ids)
    # Player ids are the columns in this dataframe
    df = pd.DataFrame()
    judge_pos = 0
    for i in range(start_round, n_rounds + start_round):
        round_list = []
        for p in player_ids:
            round_list.append({
                'player_id': p,
                'game_round_key': i,
                'is_judge': player_ids[judge_pos] == p,
                'score': 0
            })

        # Determine winner
        df = pd.concat([df, pd.DataFrame(round_list)])
        if judge_pos < len(player_ids) - 1:
            judge_pos += 1
        else:
            judge_pos = 0

    df.loc[(df['player_id'] == winner_id) & (df['is_judge'] == False) & (df['game_round_key']), 'score'] = 1

    return df
