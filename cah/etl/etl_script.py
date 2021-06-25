from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from easylogger import Log
from slacktools import SecretStore, GSheetReader, SlackTools
from cah.model import Base, Decks, QuestionCards, AnswerCards, Players
from cah.cards import QuestionCard


_log = Log('cah-etl', log_level_str='DEBUG', log_to_file=True)

_log.debug('Opening up the database...')
eng = create_engine('sqlite:////home/bobrock/data/cah_db.db')
_log.debug('Dropping existing deck and card tables...')
Base.metadata.drop_all(bind=eng, tables=[Decks.__table__, QuestionCards.__table__, AnswerCards.__table__])
_log.debug('Establishing schema...')
Base.metadata.create_all(eng)
# Bind the engine to the metadata of the Base class so that the declaratives can be accessed through a DBSession
#   instance
Base.metadata.bind = eng
DBSession = sessionmaker(bind=eng)
# A DBSession() instance establises all conversations with the database
#   and represents a 'staging zone' for all the objects loaded into the database session object
session = DBSession()

_log.debug('Authenticating credentials for services...')
credstore = SecretStore('secretprops-bobdev.kdbx')
cah_creds = credstore.get_key_and_make_ns('wizzy')
gsr = GSheetReader(sec_store=credstore, sheet_key=cah_creds.spreadsheet_key)
st = SlackTools(credstore, 'wizzy', _log)

decks = []
for sht in gsr.sheets:
    if not sht.title.startswith('x_'):
        # Likely a deck
        decks.append(sht.title)

_log.debug('Processing deck info...')
#  Read in deck info
for deck in decks:
    _log.debug(f'Working on deck {deck}')
    deck_df = gsr.get_sheet(deck)
    questions = deck_df['questions'].unique().tolist()
    answers = deck_df['answers'].unique().tolist()
    # Create the deck in the deck table, get the id
    _log.debug('Loading deck into deck table')
    deck_item = Decks(name=deck)
    session.add(deck_item)
    session.commit()
    _log.debug(f'Retrieved deck id of {deck_item.id}')

    # Now load questions and answers into the tables
    for question in questions:
        question_card = QuestionCard(txt=question)
        session.add(QuestionCards(deck_id=deck_item.id, responses_required=question_card.required_answers,
                                  card_text=question_card.txt))
    session.add_all([AnswerCards(deck_id=deck_item.id, card_text=x) for x in answers])
    session.commit()
    _log.debug(f'For deck {deck}, questions {len(questions)}:{len(session.query(QuestionCards).all())},'
               f' answers: {len(answers)}:{len(session.query(AnswerCards).all())}')

# Read in user info
_log.debug('Loading deck into deck table')
users = st.get_channel_members('CMEND3W3H')
session.add_all([Players(slack_id=x['id'], name=x['display_name']) for x in users])
session.commit()
