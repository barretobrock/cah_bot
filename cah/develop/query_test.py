from typing import (
    Dict,
    Type,
    Union
)
import pandas as pd
from easylogger import Log
from slacktools import (
    SecretStore,
    SlackTools
)
from cah.model import (
    TableAnswerCard,
    TableGame,
    TableGameRound,
    TablePlayerRound,
)
from cah.db_eng import WizzyPSQLClient
from cah.settings import auto_config


class Qtest:
    """For holding all the various ETL processes, delimited by table name or function of data stored"""

    def __init__(self, env: str = 'dev'):
        self.log = Log('vik-etl', log_level_str='DEBUG', log_to_file=True)
        self.log.debug('Optaining credential file...')
        credstore = SecretStore('secretprops-bobdev.kdbx')

        self.log.debug('Opening up the database...')
        db_props = credstore.get_entry(f'davaidb-{env}').custom_properties
        self.psql_client = WizzyPSQLClient(props=db_props, parent_log=self.log)
        self.st = SlackTools(credstore, auto_config.BOT_NICKNAME, self.log)

    def game_stats(self):
        def get_duration_stats(tbl: Type[Union[TableGame, TableGameRound]]) -> Dict[str, float]:
            """Retrieves min max median duration stats from a table with start and end times"""

            with self.psql_client.session_mgr() as session:
                if tbl.__tablename__ == 'games':
                    result_q = session.query(tbl.start_time, tbl.end_time)
                else:
                    result_q = session.query(tbl.start_time, tbl.end_time, tbl.game_id)

                df = pd.read_sql_query(result_q.statement, con=session.bind.engine)
            total = df.shape[0]
            # Filter out unfinished before calculating duration
            df = df[~df['end_time'].isnull()]
            df['duration'] = df['end_time'] - df['start_time']
            dur = df['duration']
            return {
                'total': total,
                'min': dur.min(),
                'median': dur.median(),
                'max': dur.max()
            }
        # General game stats
        #   - Number of games
        #   - median duration
        #   - longest game
        #   - shortest game - decknukes per game
        games_dur_stats = get_duration_stats(TableGame)

        # Round stats
        #   - Median number of rounds per game
        #   - longest shortest median round
        rounds_dur_stats = get_duration_stats(TableGameRound)

        # Card stats
        #   - most chosen
        with self.psql_client.session_mgr() as session:
            a_cards_result = session.query(
                TableAnswerCard.card_text,
                TableAnswerCard.times_chosen,
                TableAnswerCard.times_burned,
                TableAnswerCard.times_picked,
            )
        a_cards_df = pd.read_sql_query(a_cards_result.statement, con=session.bind.engine)
        n_cards = a_cards_df.shape[0]
        most_chosen = a_cards_df.loc[a_cards_df['times_chosen'].idxmax()]
        most_chosen_text = most_chosen.card_text
        most_chosen_val = most_chosen.times_chosen

        # Player stats
        #   - least/most likely to have caught a decknuke
        #   - longest non-judge streak
        with self.psql_client.session_mgr() as session:
            playerround_result = session.query(
                TablePlayerRound.player_id,
                TablePlayerRound.game_id,
                TablePlayerRound.round_id,
                TablePlayerRound.is_judge,
                TablePlayerRound.score
            )
        pr_df = pd.read_sql_query(playerround_result.statement, con=session.bind.engine)
        streak_df = pr_df.loc[~pr_df.is_judge, :]
        streak_df = streak_df.pivot_table(index='round_id', columns='player_id', values='score').fillna(0)
        streaks = pd.DataFrame()
        for col in streak_df.columns:
            group = (streak_df.loc[:, col] != streak_df.loc[:, col].shift()).cumsum()
            streaks[col] = streak_df.loc[:, col].groupby(group).cumsum()
        longest_streak = streaks.idxmax()


if __name__ == '__main__':
    from sqlalchemy.sql import (
        func,
        and_
    )

    qtest = Qtest(env='dev')

    with qtest.psql_client.session_mgr() as session:
        pass
