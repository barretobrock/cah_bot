import traceback
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union
)
from sqlalchemy.orm import Session
from loguru import logger
from slacktools.db_engine import PSQLClient
from cah.model import (
    SettingType,
    CahErrorType,
    TableCahError,
    TablePlayer,
    TableSetting
)


class WizzyPSQLClient(PSQLClient):
    """Creates Postgres connection engine"""

    def __init__(self, props: Dict, parent_log: logger, **kwargs):
        _ = kwargs
        super().__init__(props=props, parent_log=parent_log)

    def get_setting(self, setting: SettingType) -> Optional[Union[int, bool]]:
        """Attempts to return a given setting"""
        self.log.debug(f'Received request for setting: {setting.name}')
        with self.session_mgr() as session:
            result = session.query(TableSetting).filter(TableSetting.setting_type == setting).one_or_none()
            if result is None:
                self.log.debug('Setting was None.')
                return result

            if setting.name.startswith('IS_'):
                # Boolean
                self.log.debug(f'Returning: {result.setting_int == 1}')
                return result.setting_int == 1
            self.log.debug(f'Returning: {result.setting_int}')
            return result.setting_int

    def set_setting(self, setting: SettingType, setting_val: Union[int, bool]):
        """Attempts to set a given setting"""
        self.log.debug(f'Received request to set setting: {setting.name} to {setting_val}')
        with self.session_mgr() as session:
            session.query(TableSetting).filter(TableSetting.setting_type == setting).update(
                {TableSetting.setting_int: setting_val}
            )

    def get_player_from_hash(self, user_hash: str) -> Optional[TablePlayer]:
        """Takes in a slack user hash, outputs the expunged object, if any"""
        self.log.debug(f'Received request to fetch player: {user_hash}')
        with self.session_mgr() as session:
            user = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == user_hash).one_or_none()
            if user is not None:
                session.expunge(user)
        return user

    def get_active_players(self) -> List[TablePlayer]:
        """Retrieves a list of active players"""
        self.log.debug('Received request to fetch all active players')
        with self.session_mgr() as session:
            players = session.query(TablePlayer).filter(TablePlayer.is_active).all()
            session.expunge_all()
        return players

    def set_active_players(self, player_hashes: List[str]):
        """Retrieves a list of active players, sets them as active and anyone not in that list as inactive"""
        self.log.debug(f'Received request to set {len(player_hashes)} players as active.')
        with self.session_mgr() as session:
            players = session.query(TablePlayer).all()
            player: TablePlayer
            for player in players:
                player.is_active = player.slack_user_hash in player_hashes
            session.add_all(players)

    def refresh_table_object(self, tbl_obj, session: Session = None):
        """Refreshes a table object by adding it to the session, committing and refreshing it before
        removing it from the session"""

        def _refresh(sess: Session, tbl) -> Any:
            # Bind to session
            sess.add(tbl)
            # Prime, pull down changes
            sess.commit()
            # Populate changes to obj
            sess.refresh(tbl)
            # Remove obj from session
            sess.expunge(tbl)

        self.log.debug('Received request to refresh object...')
        if session is None:
            with self.session_mgr() as session:
                tbl_obj = _refresh(sess=session, tbl=tbl_obj)
        else:
            # Working in an existing session
            tbl_obj = _refresh(sess=session, tbl=tbl_obj)
        return tbl_obj

    def log_cah_error_to_db(self, e: Exception, error_type: CahErrorType, player_key: int = None,
                            player_round_key: int = None, game_round_key: int = None, game_key: int = None):
        """Logs error info to the service_error_log table"""

        err = TableCahError(
            error_type=error_type,
            error_class=e.__class__.__name__,
            error_text=str(e),
            error_traceback=''.join(traceback.format_tb(e.__traceback__)),
            player_key=player_key,
            player_round_key=player_round_key,
            game_round_key=game_round_key,
            game_key=game_key,
        )
        with self.session_mgr() as session:
            session.add(err)
