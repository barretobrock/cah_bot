import re
from typing import List

from pukr import get_logger
from slacktools import (
    SecretStore,
    SlackTools,
)
from slacktools.gsheet import GSheetAgent
from sqlalchemy.sql import not_

from cah.core.common_methods import refresh_players_in_channel
from cah.db_eng import WizzyPSQLClient
from cah.model import (
    Base,
    RipType,
    SettingType,
    TableAnswerCard,
    TableCahError,
    TableDeck,
    TableGame,
    TableGameRound,
    TableHonorific,
    TablePlayer,
    TablePlayerHand,
    TablePlayerPick,
    TablePlayerRound,
    TableQuestionCard,
    TableRip,
    TableSetting,
    TableTask,
    TableTaskParameter,
)
from cah.settings import Development


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
        TablePlayerHand,
        TablePlayerPick,
        TablePlayerRound,
        TableQuestionCard,
        TableRip,
        TableSetting,
        TableTask,
        TableTaskParameter
    ]

    def __init__(self, tables: List = None, env: str = 'dev', drop_all: bool = True, incl_services: bool = True):
        self.log = get_logger()
        self.log.debug('Obtaining credential file...')
        Development.load_secrets()
        props = Development.SECRETS

        self.log.debug('Opening up the database...')
        self.psql_client = WizzyPSQLClient(props=props, parent_log=self.log)

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

        if incl_services:
            credstore = SecretStore('secretprops-davaiops.kdbx')
            cah_creds = credstore.get_key_and_make_ns(Development.BOT_NICKNAME)
            self.gsr = GSheetAgent(sec_store=credstore, sheet_key=cah_creds.spreadsheet_key)
            self.st = SlackTools(props=props, main_channel=Development.MAIN_CHANNEL, use_session=False)
            self.log.debug('Completed loading services')

    def etl_bot_settings(self):
        self.log.debug('Working on settings...')
        bot_settings = []
        for bot_setting in list(SettingType):
            val_int = val_str = None
            if bot_setting.name.startswith('IS_'):
                # All current booleans will be True
                value = 1
            else:
                # Int
                if 'DECKNUKE' in bot_setting.name:
                    value = -3
                elif bot_setting == SettingType.JUDGE_ORDER_DIVIDER:
                    value = ':shiny_arrow:'
                elif bot_setting == SettingType.JUDGE_ORDER:
                    value = ''
                else:
                    value = 0
            if isinstance(value, int):
                val_int = value
            elif isinstance(value, str):
                val_str = value
            bot_settings.append(TableSetting(setting_type=bot_setting, setting_int=val_int, setting_str=val_str))

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
                    if not isinstance(txt, str):
                        continue
                    if col == 'questions':
                        # Generate a question card to leverage the response number prediction
                        req_ans = self.determine_required_answers(txt=txt)
                        card_objs.append(TableQuestionCard(card_text=txt, deck_key=deck.deck_id,
                                                           responses_required=req_ans))
                    else:
                        card_objs.append(TableAnswerCard(card_text=txt, deck_key=deck.deck_id))
            # Now load questions and answers into the tables
            with self.psql_client.session_mgr() as session:
                session.add_all(card_objs)
            self.log.debug(f'For deck: {deck}, loaded {len(card_objs)} cards.')

    @staticmethod
    def determine_required_answers(txt: str) -> int:
        """Determines the number of required answer cards for the question"""
        blank_matcher = re.compile(r'(_+)', re.IGNORECASE)
        match = blank_matcher.findall(txt)
        if match is None:
            return 1
        elif len(match) == 0:
            return 1
        else:
            return len(match)

    def etl_rips(self):
        DECKNUKE_RIPS = [
            'LOLOLOLOLOL HOW DAT DECKNUKE WORK FOR YA NOW??',
            'WADDUP DECKNUKE',
            'they just smashed that decknuke button. let\'s see how it works out for them cotton',
            '“Enola” is just alone bakwards, which is what this decknuker is',
            'This mf putin in a Deck Nuke',
            'You decknuked and won. Congratulations on being bad at this game.',
            ':alphabet-yellow-w::alphabet-yellow-a::alphabet-yellow-d::alphabet-yellow-d::alphabet-yellow-u:'
            ':alphabet-yellow-p::blank::alphabet-yellow-d::alphabet-yellow-e::alphabet-yellow-c:'
            ':alphabet-yellow-k::alphabet-yellow-n::alphabet-yellow-u::alphabet-yellow-k::alphabet-yellow-e:',
        ]
        rip_objs = []
        for rip in DECKNUKE_RIPS:
            rip_objs.append(TableRip(rip_type=RipType.DECKNUKE, text=rip))
        with self.psql_client.session_mgr() as session:
            session.add_all(rip_objs)

    def etl_players(self):
        """ETL for possible players"""
        # For ETL we'll use #general (CMEND3W3H)
        refresh_players_in_channel(channel='CMEND3W3H', eng=self.psql_client, st=self.st, log=self.log)
        with self.psql_client.session_mgr() as session:
            uids = [x.slack_user_hash for x in session.query(TablePlayer).all()]

        # Iterate through players in channel, set active if they're in the channel
        active_users = []
        for user in self.st.get_channel_members(self.st.main_channel):
            if user.id in uids:
                active_users.append(user.id)
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
