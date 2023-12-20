from loguru import logger
import pandas as pd
from sqlalchemy.sql import (
    and_,
    func,
)

from cah.db_eng import WizzyPSQLClient
from cah.model import (
    TablePlayer,
    TablePlayerRound,
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

    def get_score_data_for_display_points(self, game_id: int, game_round_id: int) -> pd.DataFrame:
        """Gets the details for display_points when a current game is in progress"""
        with self.eng.session_mgr() as session:
            prev_round_game_score_subq = (session.query(
                TablePlayer.player_id,
                func.sum(TablePlayerRound.score).label('prev')
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id,
                TablePlayerRound.game_round_key < game_round_id - 1
            ).group_by(TablePlayer.player_id).subquery())

            current_round_game_score_subq = (session.query(
                TablePlayer.player_id,
                func.sum(TablePlayerRound.score).label('current')
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id
            ).group_by(TablePlayer.player_id).subquery())

            overall_prev_score_subq = (session.query(
                TablePlayer.player_id,
                func.sum(TablePlayerRound.score).label('overall_prev')
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(and_(
                TablePlayer.is_active,
                TablePlayerRound.game_round_key < game_round_id - 1
            )).group_by(TablePlayer.player_id).subquery())

            overall_current_score_subq = (session.query(
                TablePlayer.player_id,
                func.sum(TablePlayerRound.score).label('overall_current')
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(and_(
                TablePlayer.is_active
            )).group_by(TablePlayer.player_id).subquery())

            main_query = session.query(
                TablePlayer.player_id,
                TablePlayer.display_name,
                func.coalesce(func.sum(overall_current_score_subq.c.overall_current), 0).label('overall_current'),
                func.coalesce(func.sum(overall_prev_score_subq.c.overall_prev), 0).label('overall_prev'),
                func.coalesce(func.sum(current_round_game_score_subq.c.current), 0).label('current'),
                func.coalesce(func.sum(prev_round_game_score_subq.c.prev), 0).label('prev'),
            ).outerjoin(
                overall_current_score_subq, TablePlayer.player_id == overall_current_score_subq.c.player_id
            ).outerjoin(
                overall_prev_score_subq, TablePlayer.player_id == overall_prev_score_subq.c.player_id
            ).outerjoin(
                current_round_game_score_subq, TablePlayer.player_id == current_round_game_score_subq.c.player_id
            ).outerjoin(
                prev_round_game_score_subq, TablePlayer.player_id == prev_round_game_score_subq.c.player_id
            ).group_by(TablePlayer.player_id, TablePlayer.display_name)
            return pd.read_sql(main_query.statement, session.bind)

    def get_player_rounds_in_game(self, game_id: int) -> pd.DataFrame:
        with self.eng.session_mgr() as session:
            all_rounds = session.query(
                TablePlayer.player_id,
                TablePlayerRound.game_round_key,
                TablePlayerRound.is_judge,
                TablePlayerRound.is_nuked_hand_caught,
                TablePlayerRound.score
            ).join(TablePlayerRound, TablePlayerRound.player_key == TablePlayer.player_id).filter(
                TablePlayerRound.game_key == game_id
            ).all()
            return pd.DataFrame(all_rounds)
