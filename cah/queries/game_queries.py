from typing import (
    Dict,
    List,
    Optional,
    TypedDict,
)

from loguru import logger
import pandas as pd
from sqlalchemy.sql import (
    and_,
    func,
)

from cah.db_eng import WizzyPSQLClient
from cah.model import (
    RipType,
    TableAnswerCard,
    TableGameRound,
    TablePlayer,
    TablePlayerPick,
    TableQuestionCard,
    TableRip,
)


class PickItemType(TypedDict):
    card_key: int
    card_text: str
    card_order: int


class GameQueries:
    """Storing the query methodology here for easier mocking"""

    def __init__(self, eng: WizzyPSQLClient, log: logger):
        self.eng = eng
        self.log = log.bind(child_name=self.__class__.__name__)

    def get_player_picks(self, game_round_id: int) -> Dict[str, List[PickItemType]]:
        """Gets the player picks for the round

        Notes
            Expected structure (e.g., for a round requiring 2 answers...):
            {
                {player_hash}: [
                    {
                        card_key: 12398
                        card_text: 'Something...'
                        card_order: 0
                    }, {
                        card_key: 13443
                        card_text: 'Another...'
                        card_order: 1
                    }
                ]
                ...
            }
        """
        with self.eng.session_mgr() as session:
            picks = session.query(
                TablePlayerPick.pick_id,
                TablePlayerPick.answer_card_key,
                TablePlayerPick.slack_user_hash,
                TablePlayerPick.card_order,
                TableAnswerCard.card_text
            ).join(TableAnswerCard, TablePlayerPick.answer_card_key == TableAnswerCard.answer_card_id).\
                filter(TablePlayerPick.game_round_key == game_round_id).order_by(TablePlayerPick.pick_id).all()
            session.expunge_all()
        player_picks: Dict[str, List[PickItemType]]
        player_picks = {}
        for pick in picks:
            # Make the dictionary for the pick
            pick_dict: PickItemType
            pick_dict = {
                'card_key': pick.answer_card_key,
                'card_text': pick.card_text,
                'card_order': pick.card_order
            }
            if pick.slack_user_hash in player_picks.keys():
                # Add another pick to the dictionary
                player_picks[pick.slack_user_hash].append(pick_dict)
            else:
                player_picks[pick.slack_user_hash] = [pick_dict]
        for player, pick_list in player_picks.items():
            pick_list.sort(key=lambda item: item.get('card_order'))
        return player_picks

    def get_current_question(self, game_round_id: int) -> Optional[TableQuestionCard]:
        if game_round_id is None:
            return None
        with self.eng.session_mgr() as session:
            question = session.query(TableQuestionCard).\
                join(TableGameRound, TableGameRound.question_card_key == TableQuestionCard.question_card_id).\
                filter(TableGameRound.game_round_id == game_round_id).one_or_none()
            session.expunge(question)
            return question

    def get_rip(self, rip_type: RipType) -> str:
        with self.eng.session_mgr() as session:
            rip = session.query(TableRip).filter(TableRip.rip_type == rip_type).\
                order_by(func.random()).limit(1).one_or_none()
            if rip is None:
                return 'I....got nothing. Consider yourself spared from rippin this time.'
            return rip.text

    def get_game_stats(self) -> Dict:
        with self.eng.session_mgr() as session:
            # round duration
            round_stats = session.query(
                func.avg(TableGameRound.end_time - TableGameRound.start_time).label('avg_round'),
                func.min(TableGameRound.end_time - TableGameRound.start_time).label('min_round'),
                func.max(TableGameRound.end_time - TableGameRound.start_time).label('max_round')
            ).filter(and_(
                TableGameRound.end_time.isnot(None)
            )).all()
            avg_round, min_round, max_round = round_stats[0]

            # pick/choose stats
            pick_stats_q = session.query(
                TableGameRound.game_round_id,
                TableGameRound.start_time.label('round_start'),
                TablePlayer.display_name,
                TablePlayerPick.created_date.label('pick_timestamp'),
                (TablePlayerPick.created_date - TableGameRound.start_time).label('duration_before_pick'),
                TableGameRound.end_time.label('round_end')
            ).join(TablePlayerPick, TablePlayerPick.game_round_key == TableGameRound.game_round_id).\
                join(TablePlayer, TablePlayerPick.slack_user_hash == TablePlayer.slack_user_hash).\
                filter(and_(
                    TableGameRound.end_time.isnot(None)
                ))

            pick_stats_df = pd.read_sql(pick_stats_q.statement, session.bind)
            slowest_pick_idx = pick_stats_df['duration_before_pick'].idxmax()
            slowest_pick = pick_stats_df.loc[slowest_pick_idx, 'duration_before_pick']
            slowest_pick_player = pick_stats_df.loc[slowest_pick_idx, 'display_name']

            fastest_pick_idx = pick_stats_df['duration_before_pick'].idxmin()
            fastest_pick = pick_stats_df.loc[fastest_pick_idx, 'duration_before_pick']
            fastest_pick_player = pick_stats_df.loc[fastest_pick_idx, 'display_name']

            avg_pick_time = pick_stats_df['duration_before_pick'].mean()

            # TODO: More stats
            #   % of time that a winner is the judge next

            return {
                'Avg Round': avg_round,
                'Min Round': min_round,
                'Max Round': max_round,
                'Slowest Pick': slowest_pick,
                'Slowest Pickler': slowest_pick_player,
                'Fastest Pick': fastest_pick,
                'fastest pickler': fastest_pick_player,
                'avg pick time': avg_pick_time,
                'mostest averagest pickler': '????',
                'weirdest pickler': 'whichever name is barry\'s',
                '% winner next round judge': 'TBD'
            }
