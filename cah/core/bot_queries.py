from typing import (
    List,
    Optional,
    Union
)
import pandas as pd
from loguru import logger
from sqlalchemy.sql import (
    and_,
    func,
    not_,
    or_
)
from sqlalchemy.orm.attributes import InstrumentedAttribute
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    TablePlayer,
    TablePlayerRound
)


class BotQueries:
    """Storing the query methodology here for easier mocking"""

    def __init__(self, eng: WizzyPSQLClient, log: logger):
        self.eng = eng
        self.log = log.bind(child_name=self.__class__.__name__)

    def get_overall_score(self, col_name: str = 'overall') -> pd.DataFrame:
        with self.eng.session_mgr() as session:
            overall = session.query(
                TablePlayer.player_id,
                TablePlayer.display_name,
                func.sum(TablePlayerRound.score).label(col_name)
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayer.is_active
            ).group_by(TablePlayer.player_id).all()
            return pd.DataFrame(overall)

    def get_overall_score_at_round(self, game_round_id: int = None, col_name: str = 'overall') -> pd.DataFrame:
        with self.eng.session_mgr() as session:
            overall_at_round = session.query(
                TablePlayer.player_id,
                TablePlayer.display_name,
                func.sum(TablePlayerRound.score).label(col_name)
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(and_(
                TablePlayer.is_active,
                TablePlayerRound.game_round_key < game_round_id - 1
            )).group_by(TablePlayer.player_id).all()
            return pd.DataFrame(overall_at_round)

    def get_current_game_score(self, game_id: int, col_name: str = 'current') -> pd.DataFrame:
        with self.eng.session_mgr() as session:
            current = session.query(
                TablePlayer.player_id,
                TablePlayer.display_name,
                func.sum(TablePlayerRound.score).label(col_name),
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id
            ).group_by(TablePlayer.player_id).all()
            return pd.DataFrame(current)

    def get_game_score_at_round(self, game_id: int, game_round_id: int, col_name: str = 'prev') -> pd.DataFrame:
        with self.eng.session_mgr() as session:
            prev_round = session.query(
                TablePlayer.player_id,
                TablePlayer.display_name,
                func.sum(TablePlayerRound.score).label(col_name),
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id,
                TablePlayerRound.game_round_key < game_round_id
            ).group_by(TablePlayer.player_id).all()
            return pd.DataFrame(prev_round)



