from typing import List
from sqlalchemy.sql import not_
from easylogger import Log
from slacktools import (
    SecretStore,
    GSheetReader,
    SlackTools
)
from cah.model import (
    Base,
    SettingType,
    TableAnswerCard,
    TableDeck,
    TableCahError,
    TableGame,
    TableGameRound,
    TableHonorific,
    TablePlayer,
    TablePlayerRound,
    TableQuestionCard,
    TableSetting
)
from cah.db_eng import WizzyPSQLClient
from cah.settings import auto_config
from cah.core.cards import QuestionCard
from cah.core.common_methods import refresh_players_in_channel


class ETL:
    """For holding all the various ETL processes, delimited by table name or function of data stored"""

    ALL_TABLES = [
        TableAnswerCard,
        TableDeck,
        TableCahError,
        TableGame,
        TableGameRound,
        TableHonorific,
        TablePlayer,
        TablePlayerRound,
        TableQuestionCard,
        TableSetting
    ]

    def __init__(self, tables: List = None, env: str = 'dev', drop_all: bool = True):
        self.log = Log('cah-etl', log_level_str='DEBUG', log_to_file=True)
        self.log.debug('Obtaining credential file...')
        credstore = SecretStore('secretprops-davaiops.kdbx')

        self.log.debug('Opening up the database...')
        db_props = credstore.get_entry(f'davaidb-{env}').custom_properties
        self.psql_client = WizzyPSQLClient(props=db_props, parent_log=self.log)

        # Determine tables to drop
        self.log.debug(f'Working on tables: {tables} from db...')
        tbl_objs = []
        for table in tables:
            tbl_objs.append(
                Base.metadata.tables.get(f'{table.__table_args__.get("schema")}.{table.__tablename__}'))
        if drop_all:
            # We're likely doing a refresh - drop/create operations will be for all object
            self.log.debug(f'Dropping {len(tbl_objs)} listed tables...')
            Base.metadata.drop_all(self.psql_client.engine, tables=tbl_objs)
        self.log.debug(f'Creating {len(tbl_objs)} listed tables...')
        Base.metadata.create_all(self.psql_client.engine, tables=tbl_objs)

        self.log.debug('Authenticating credentials for services...')
        cah_creds = credstore.get_key_and_make_ns(auto_config.BOT_NICKNAME)
        self.gsr = GSheetReader(sec_store=credstore, sheet_key=cah_creds.spreadsheet_key)
        self.st = SlackTools(credstore, auto_config.BOT_NICKNAME, self.log)
        self.log.debug('Completed loading services')

    def etl_bot_settings(self):
        self.log.debug('Working on settings...')
        bot_settings = []
        for bot_setting in list(SettingType):
            if bot_setting.name.startswith('IS_'):
                # All current booleans will be True
                value = 1
            else:
                # Int
                if 'DECKNUKE' in bot_setting.name:
                    value = 3
                else:
                    value = 0
            bot_settings.append(TableSetting(setting_type=bot_setting, setting_int=value))

        with self.psql_client.session_mgr() as session:
            self.log.debug(f'Adding {len(bot_settings)} bot settings.')
            session.add_all(bot_settings)

    def etl_decks(self):
        """ETL for decks and card tables"""
        decks = []  # type: List[TableDeck]
        for sht in self.gsr.sheets:
            if not sht.title.startswith('x_'):
                # Likely a deck
                decks.append(TableDeck(name=sht.title))
        with self.psql_client.session_mgr() as session:
            session.add_all(decks)
            # Add decks to db with commit
            session.commit()
            for deck in decks:
                # Refresh each item now to pull in their id
                session.refresh(deck)
            # Remove these items from the session so they'll still be accessible after session closes
            session.expunge_all()

        self.log.debug('Processing deck info...')
        #  Read in deck info
        for deck in decks:
            card_objs = []
            self.log.debug(f'Working on deck {deck}')
            df = self.gsr.get_sheet(deck.name)
            for col in ['questions', 'answers']:
                txt_list = df.loc[
                    (~df[col].isnull()) & (df[col].str.strip() != ''), col
                ].str.strip().unique().tolist()
                for txt in txt_list:
                    if col == 'questions':
                        # Generate a question card to leverage the response number prediction
                        card = QuestionCard(txt=txt, card_id=0)
                        card_objs.append(TableQuestionCard(card_text=card.txt, deck_key=deck.deck_id,
                                                           responses_required=card.required_answers))
                    else:
                        card_objs.append(TableAnswerCard(card_text=txt, deck_key=deck.deck_id))
            # Now load questions and answers into the tables
            with self.psql_client.session_mgr() as session:
                session.add_all(card_objs)
            self.log.debug(f'For deck: {deck}, loaded {len(card_objs)} cards.')

    def etl_players(self):
        """ETL for possible players"""
        # For ETL we'll use #general (CMEND3W3H)
        refresh_players_in_channel(channel='CMEND3W3H', eng=self.psql_client, st=self.st, log=self.log)
        with self.psql_client.session_mgr() as session:
            uids = [x.slack_user_hash for x in session.query(TablePlayer).all()]

        # Iterate through players in channel, set active if they're in the channel
        active_users = []
        for user in self.st.get_channel_members('CMPV3K8AE'):
            if user['id'] in uids:
                active_users.append(user['id'])
        self.log.debug(f'Found {len(active_users)} in #cah. Setting others to inactive...')
        with self.psql_client.session_mgr() as session:
            session.query(TablePlayer).filter(not_(TablePlayer.slack_user_hash.in_(active_users))).update({
                TablePlayer.is_active: False
            })

    def etl_honorific(self):

        honorifics = {
            (-200, -7): ['loser', 'toady', 'weak', 'despised', 'defeated', 'under-under-underdog'],
            (-6, -3): ['concerned', 'bestumbled', 'under-underdog'],
            (-2, 0): ['temporarily disposed', 'momentarily disheveled', 'underdog'],
            (1, 3): ['lackey', 'intern', 'doormat', 'underling', 'deputy', 'amateur', 'newcomer'],
            (4, 6): ['young padawan', 'master apprentice', 'rookie', 'greenhorn', 'fledgling', 'tenderfoot'],
            (7, 9): ['honorable', 'respected and just', 'cold and yet still fair'],
            (10, 12): ['worthy inheriter of (mo|da)ddy\'s millions', '(mo|fa)ther of dragons',
                       'most excellent', 'knowledgeable', 'wise'],
            (13, 15): ['elder', 'ruler of the lower cards', 'most fair dictator of difficult choices'],
            (16, 18): ['benevolent and omniscient chief of dutiful diddling', 'supreme high chancellor of '],
            (19, 21): ['almighty veteran diddler', 'ancient diddle dealer from before time began',
                       'sage of the diddles'],
            (22, 500): ['bediddled', 'grand bediddler', 'most wise in the ways of the diddling',
                        'pansophical bediddled sage of the dark cards']
        }
        tbl_objs = []
        for rng, name_list in honorifics.items():
            for name in name_list:
                tbl_objs.append(TableHonorific(text=f'the {name}'.title(), score_range=rng))
        self.log.debug(f'Loading {len(tbl_objs)} honorifics to the table...')
        with self.psql_client.session_mgr() as session:
            session.add_all(tbl_objs)


if __name__ == '__main__':
    etl = ETL(tables=ETL.ALL_TABLES, env='dev', drop_all=True)
    etl.etl_bot_settings()
    etl.etl_decks()
    etl.etl_players()
    etl.etl_honorific()
