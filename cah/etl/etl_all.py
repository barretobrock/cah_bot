from typing import List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from easylogger import Log
from slacktools import SecretStore, GSheetReader, SlackTools
import cah.cards as cahds
from cah.model import Base, TableDecks, TableQuestionCards, TableAnswerCards, TablePlayers


class ETL:
    """For holding all the various ETL processes, delimited by table name or function of data stored"""

    def __init__(self, tables: List[str]):
        self.log = Log('cah-etl', log_level_str='DEBUG', log_to_file=True)
        self.log.debug('Opening up the database...')
        self.eng = create_engine('sqlite:////home/bobrock/data/cahdb.db')

        # Determine tables to drop
        self.log.debug(f'Dropping tables: {tables} from db...')
        tbl_objs = []
        for table in tables:
            tbl_objs.append(Base.metadata.tables.get(table))
        Base.metadata.drop_all(self.eng, tables=tbl_objs, checkfirst=True)
        self.log.debug('Establishing database...')
        Base.metadata.create_all(self.eng)
        self.session = self._make_session()

        self.log.debug('Authenticating credentials for services...')
        credstore = SecretStore('secretprops-bobdev.kdbx')
        cah_creds = credstore.get_key_and_make_ns('wizzy')
        self.gsr = GSheetReader(sec_store=credstore, sheet_key=cah_creds.spreadsheet_key)
        self.st = SlackTools(credstore, 'wizzy', self.log)

    def _make_session(self) -> Session:
        # Bind the engine to the metadata of the Base class so that
        #   the declaratives can be accessed through a DBSession instance
        Base.metadata.bind = self.eng
        DBSession = sessionmaker(bind=self.eng)
        # A DBSession() instance establises all conversations with the database
        #   and represents a 'staging zone' for all the objects loaded into the database session object
        session = DBSession()
        return session

    def etl_decks(self):
        """ETL for decks and card tables"""
        decks = []
        for sht in self.gsr.sheets:
            if not sht.title.startswith('x_'):
                # Likely a deck
                decks.append(sht.title)

        self.log.debug('Processing deck info...')
        #  Read in deck info
        for deck in decks:
            self.log.debug(f'Working on deck {deck}')
            deck_df = self.gsr.get_sheet(deck)
            questions = deck_df['questions'].unique().tolist()
            answers = deck_df['answers'].unique().tolist()
            # Create the deck in the deck table, get the id
            self.log.debug('Loading deck into deck table')
            deck_item = TableDecks(name=deck)
            self.session.add(deck_item)
            self.session.commit()
            self.log.debug(f'Retrieved deck id of {deck_item.id}')

            # Now load questions and answers into the tables
            for question in questions:
                if question == '':
                    continue
                question_card = cahds.QuestionCard(txt=question, card_id=000)
                self.session.add(
                    TableQuestionCards(deck_id=deck_item.id, responses_required=question_card.required_answers,
                                       card_text=question_card.txt))
            self.session.add_all([TableAnswerCards(deck_id=deck_item.id, card_text=x) for x in answers if x != ''])
            self.session.commit()
            added_questions = self.session.query(TableQuestionCards).join(TableDecks).filter(
                TableDecks.name == deck).all()
            added_answers = self.session.query(TableAnswerCards).join(TableDecks)\
                .filter(TableDecks.name == deck).all()
            self.log.debug(f'For deck {deck}, questions {len(questions)}:{len(added_questions)},'
                           f' answers: {len(answers)}:{len(added_answers)}')

    def etl_players(self):
        """ETL for decks and card tables"""

        # Read in user info
        self.log.debug('Loading players into player table')
        users = self.st.get_channel_members('CMEND3W3H')
        self.session.add_all([TablePlayers(slack_id=x['id'], name=x['display_name']) for x in users
                              if not x['is_bot']])
        self.session.commit()


if __name__ == '__main__':
    etl = ETL(tables=['decks', 'question_cards', 'answer_cards', 'players'])
    etl.etl_decks()
    etl.etl_players()
