from pukr import get_logger
from slacktools.secretstore import SecretStore
from slacktools.db_engine import PSQLClient
from cah.model import (
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
from cah.etl.etl_gs import ETL


TARGET_DB = 'PROD'
SOURCE_DB = 'DEV'

log = get_logger('db_transfer')

credstore = SecretStore('secretprops-davaiops.kdbx')
# Load target and source dbs
tgt_props = credstore.get_entry(f'davaidb-{TARGET_DB.lower()}').custom_properties
tgt_db = PSQLClient(tgt_props, parent_log=log)
src_props = credstore.get_entry(f'davaidb-{SOURCE_DB.lower()}').custom_properties
src_db = PSQLClient(src_props, parent_log=log)

# Instantiate the process to recreate the schema and, if needed, drop all existing tables
etl = ETL(tables=ETL.ALL_TABLES, env=TARGET_DB.lower(), drop_all=True, incl_services=False)

# Begin transferring data between databases
#   tableobject: keep_stats?
tables = {
    TableTask: {
        'method': 'copy'
    },
    TableTaskParameter: {
        'method': 'copy'
    },
    TableSetting: {
        'method': 'copy'
    },
    TableHonorific: {
        'method': 'copy'
    },
    TableRip: {
        'method': 'copy'
    },
    TableDeck: {
        'method': 'copy'
    },
    TableAnswerCard: {
        'method': 'no_stats',
        'keep_cols': [TableAnswerCard.deck_key, TableAnswerCard.card_text]
    },
    TableQuestionCard: {
        'method': 'no_stats',
        'keep_cols': [TableQuestionCard.deck_key, TableQuestionCard.card_text,
                      TableQuestionCard.responses_required]
    },
    TableGame: {
        'method': 'empty'
    },
    TableGameRound: {
        'method': 'empty'
    },
    TablePlayer: {
        'method': 'no_stats',
        'keep_cols': [TablePlayer.slack_user_hash, TablePlayer.display_name, TablePlayer.is_dm_cards,
                      TablePlayer.is_auto_randpick, TablePlayer.is_auto_randchoose, TablePlayer.is_active,
                      TablePlayer.avi_url]
    },
    TablePlayerPick: {
        'method': 'empty'
    },
    TablePlayerRound: {
        'method': 'empty'
    },
    TablePlayerHand: {
        'method': 'empty'
    },
    TableCahError: {
        'method': 'empty'
    },
}

for tbl, instructions in tables.items():
    transfer_method = instructions.get('method', 'copy')
    log.debug(f'Working on table {tbl.__tablename__}. Instructions are: {transfer_method}')
    with src_db.session_mgr() as src_session, tgt_db.session_mgr() as tgt_session:
        if transfer_method == 'empty':
            log.debug('Instructions were to leave this empty. Bypassing transfer.')
            continue

        try:
            vals = src_session.query(tbl).all()
        except Exception as e:
            log.error(f'{tbl.__name__} saw an error in copying info: {e}')
            continue

        keep_cols = instructions.get('keep_cols')

        log.debug(f'Pulled {len(vals)} items... Expunging from source session.')
        src_session.expunge_all()

        if transfer_method == 'copy':
            log.debug('Beginning merge of rows into target session...')
            for i, row in enumerate(vals):
                if i % 500 == 0:
                    log.debug(f'Working on {i} of {len(vals)} ({i / len(vals):.1%})...')
                tgt_session.merge(row)
        elif transfer_method == 'no_stats':
            log.debug(f'Beginning selective transfer based on the columns to keep: {keep_cols}')
            kept_vals = []
            for val in vals:
                kept_vals.append(tbl(**{k.key: getattr(val, k.key) for k in keep_cols}))
            log.debug(f'Adding {len(kept_vals)} cleaned objects')
            tgt_session.add_all(kept_vals)
