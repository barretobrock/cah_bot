from typing import List
from random import choice
from easylogger import Log
from slacktools import SecretStore, GSheetReader, SlackTools
import cah.app as cah_app
import cah.cards as cahhds
from cah.model import Base, TableDecks, TableQuestionCards, TableAnswerCards, TablePlayers, TableGameSettings,\
    TablePlayerRounds, TableGames, TableGameRounds
from cah.etl.etl_decks import deck_tables
from cah.etl.etl_games import game_tables
from cah.etl.etl_players import player_tables
from cah.settings import auto_config


class ETL:
    """For holding all the various ETL processes, delimited by table name or function of data stored"""

    def __init__(self, tables: List[str]):
        self.log = Log('cah-etl', log_level_str='DEBUG', log_to_file=True)
        self.log.debug('Opening up the database...')
        self.session, self.eng = auto_config.SESSION(), auto_config.engine

        # Determine tables to drop
        self.log.debug(f'Dropping tables: {tables} from db...')
        tbl_objs = []
        for table in tables:
            tbl_objs.append(Base.metadata.tables.get(table))
        Base.metadata.drop_all(self.eng, tables=tbl_objs)
        self.log.debug('Establishing database...')
        Base.metadata.create_all(self.eng)

        self.log.debug('Authenticating credentials for services...')
        credstore = SecretStore('secretprops-bobdev.kdbx')
        cah_creds = credstore.get_key_and_make_ns('wizzy')
        self.gsr = GSheetReader(sec_store=credstore, sheet_key=cah_creds.spreadsheet_key)
        self.st = SlackTools(credstore, 'wizzy', self.log)

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
                question_card = cahhds.QuestionCard(txt=question, card_id=000)
                self.session.add(
                    TableQuestionCards(deck_id=deck_item.id, responses_required=question_card.required_answers,
                                       card_text=question_card.txt))
            self.session.add_all([TableAnswerCards(deck_id=deck_item.id, card_text=x) for x in answers if x != ''])
            added_questions = self.session.query(TableQuestionCards).join(TableDecks).filter(
                TableDecks.name == deck).all()
            added_answers = self.session.query(TableAnswerCards).join(TableDecks)\
                .filter(TableDecks.name == deck).all()
            self.log.debug(f'For deck {deck}, questions {len(questions)}:{len(added_questions)},'
                           f' answers: {len(answers)}:{len(added_answers)}')
        self.session.commit()

    def etl_players(self):
        """ETL for decks and card tables"""

        # Read in user info
        self.log.debug('Loading players into player table')
        users = self.st.get_channel_members('CMEND3W3H')
        self.session.add_all([TablePlayers(slack_id=x['id'], name=x['display_name']) for x in users
                              if not x['is_bot']])
        self.session.commit()

        self.log.debug(f'Loaded {len(self.session.query(TablePlayers).all())} players into table.')

    def game_sim(self):
        """Simulate db functions over a game"""
        players = self.session.query(TablePlayers).all()[:4]
        game = TableGames()
        self.session.add(game)
        self.session.commit()

        for i in range(10):
            self.log.debug(f'Beginning round {i}...')
            gameround = TableGameRounds(game_id=game.id)
            self.session.add(gameround)
            self.session.commit()
            player_rounds = []
            for p in players:
                player_round = TablePlayerRounds(player_id=p.id, game_id=game.id, round_id=gameround.id)
                self.session.add(player_round)
                player_rounds.append(player_round)
            self.session.commit()
            for p_round in player_rounds:
                p_round.score += choice(range(-3, 5))
            self.session.commit()

        ps = self.session.query(TablePlayers.total_score).all()

    def etl_games(self):
        # Add in the only row used in gamesettings
        self.session.add(TableGameSettings())
        self.session.commit()
        self.log.debug('Game settings refreshed.')


if __name__ == '__main__':
    etl = ETL(tables=deck_tables + game_tables + player_tables)
    etl.etl_decks()
    etl.etl_players()
    etl.etl_games()
