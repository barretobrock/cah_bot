import traceback
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)

from loguru import logger
from slacktools.db_engine import PSQLClient
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from cah.model import (
    CahErrorType,
    SettingType,
    TableCahError,
    TablePlayer,
    TableSetting,
)


class WizzyPSQLClient(PSQLClient):
    """Creates Postgres connection engine"""

    def __init__(self, props: Dict, **kwargs):
        _ = kwargs
        super().__init__(props=props)

    def get_setting(self, setting: SettingType) -> Optional[Union[int, bool, str]]:
        """Attempts to return a given setting"""
        logger.debug(f'Received request for setting: {setting.name}')
        with self.session_mgr() as session:
            result: TableSetting
            result = session.query(TableSetting).filter(TableSetting.setting_type == setting).one_or_none()
            if result is None:
                logger.debug('Setting was None.')
                return result

            if setting.name.startswith('IS_'):
                # Boolean
                logger.debug(f'Returning: {result.setting_int == 1}')
                return result.setting_int == 1
            if result.setting_int is None:
                # Return the string if the integer is None
                logger.debug(f'Returning str: {result.setting_str}')
                return result.setting_str
            logger.debug(f'Returning int: {result.setting_int}')
            return result.setting_int

    def set_setting(self, setting: SettingType, setting_val: Union[int, bool, str]):
        """Attempts to set a given setting"""
        logger.debug(f'Received request to set setting: {setting.name} to {setting_val}')
        with self.session_mgr() as session:
            # Settings are more likely to be integer
            setting_attr = TableSetting.setting_int
            if isinstance(setting_val, bool):
                setting_val = int(setting_val)
            elif isinstance(setting_val, str):
                # Set the attribute to change to a string instead of an integer
                setting_attr = TableSetting.setting_str
            session.query(TableSetting).filter(TableSetting.setting_type == setting).update(
                {setting_attr: setting_val}
            )

    def get_player_from_hash(self, user_hash: str) -> Optional[TablePlayer]:
        """Takes in a slack user hash, outputs the expunged object, if any"""
        return self._get_player_from(TablePlayer.slack_user_hash, user_hash)

    def get_player_from_id(self, user_id: int) -> Optional[TablePlayer]:
        """Takes in a slack user hash, outputs the expunged object, if any"""
        return self._get_player_from(TablePlayer.player_id, user_id)

    def _get_player_from(self,  attr: Union[InstrumentedAttribute, int, str],
                         value: Union[str, int]) -> Optional[TablePlayer]:
        """Takes in a slack user hash or player id, outputs the expunged object, if any"""
        logger.debug(f'Received request to fetch player via {attr.key}: {value}')
        with self.session_mgr() as session:
            user = session.query(TablePlayer).filter(attr == value).one_or_none()
            if user is not None:
                session.expunge(user)
            else:
                logger.debug('User wasn\'t found in db with provided value. Returning None.')
        return user

    def get_active_players(self) -> List[TablePlayer]:
        """Retrieves a list of active players"""
        logger.debug('Received request to fetch all active players')
        with self.session_mgr() as session:
            players = session.query(TablePlayer).filter(TablePlayer.is_active).all()
            session.expunge_all()
        return players

    def set_active_players(self, player_hashes: List[str]):
        """Retrieves a list of active players, sets them as active and anyone not in that list as inactive"""
        logger.debug(f'Received request to set {len(player_hashes)} players as active.')
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
            return tbl

        logger.debug('Received request to refresh object...')
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
