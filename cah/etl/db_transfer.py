from pathlib import Path
from pukr import get_logger
from slacktools.secretstore import SecretStore
from slacktools.db_engine import PSQLClient
from cah.model import (
    GameStatus,
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
    TableTaskParameter
)
from cah.logg import get_base_logger
from cah.etl.etl_gs import ETL


TARGET_DB = 'DEV'
SOURCE_DB = 'PROD'

log = get_logger('db_transfer')

credstore = SecretStore('secretprops-davaiops.kdbx')
# Load target and source dbs
tgt_props = credstore.get_entry(f'davaidb-{TARGET_DB.lower()}').custom_properties
tgt_db = PSQLClient(tgt_props, parent_log=log)
src_props = credstore.get_entry(f'davaidb-{SOURCE_DB.lower()}').custom_properties
src_db = PSQLClient(src_props, parent_log=log)

# Instantiate the process to recreate the schema and, if needed, drop all existing tables
etl = ETL(tables=ETL.ALL_TABLES, env=TARGET_DB.lower(), drop_all=False, incl_services=False)

# Begin transferring data between databases
tables = [
    TableTask,
    TableTaskParameter,
    # TableSetting,
    # TableHonorific,
    # TableRip,
    # TableDeck,
    # TableAnswerCard,
    # TableQuestionCard,
    # TableGame,
    TableGameRound,
    TablePlayer,
    TablePlayerPick,
    TablePlayerRound,
    TablePlayerHand,
    TableCahError,
]

for tbl in tables:
    log.debug(f'Working on table {tbl.__tablename__}')
    with src_db.session_mgr() as src_session, tgt_db.session_mgr() as tgt_session:
        try:
            vals = src_session.query(tbl).all()
        except Exception as e:
            log.error(f'{tbl.__name__} saw an error in copying info: {e}')
            continue
        log.debug(f'Pulled {len(vals)} items... Expunging from source session.')
        src_session.expunge_all()
        log.debug('Beginning merge of rows into target session...')
        for i, row in enumerate(vals):
            if i % 500 == 0:
                log.debug(f'Working on {i} of {len(vals)} ({i / len(vals):.1%})...')
            tgt_session.merge(row)
