import traceback
from typing import (
    Dict,
    Optional,
    Union
)
from contextlib import contextmanager
from sqlalchemy.engine import (
    create_engine,
    URL
)
from sqlalchemy.orm import sessionmaker
from easylogger import Log
from cah.model import (
    SettingType,
    CahErrorType,
    TableCahError,
    TablePlayer,
    TableSetting
)


class WizzyPSQLClient:
    """Creates Postgres connection engine"""

    def __init__(self, props: Dict, parent_log: Log, **kwargs):
        self.log = Log(parent_log, child_name=self.__class__.__name__)
        self.engine = create_engine(URL.create(
            drivername='postgresql+psycopg2',
            username=props.get('usr'),
            password=props.get('pwd'),
            host=props.get('host'),
            port=props.get('port'),
            database=props.get('database')
        ))
        self._dbsession = sessionmaker(bind=self.engine)

    @contextmanager
    def session_mgr(self):
        """This sets up a transactional scope around a series of operations"""
        session = self._dbsession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_setting(self, setting: SettingType) -> Optional[Union[int, bool]]:
        """Attempts to return a given setting"""
        with self.session_mgr() as session:
            result = session.query(TableSetting).filter(TableSetting.setting_type == setting).one_or_none()
            if result is None:
                return result
            if setting.name.startswith('IS_'):
                # Boolean
                return result.setting_int == 1
            return result.setting_int

    def set_setting(self, setting: SettingType, setting_val: Union[int, bool]):
        """Attempts to set a given setting"""
        with self.session_mgr() as session:
            session.query(TableSetting).filter(TableSetting.setting_type == setting).update(
                {TableSetting.setting_int: setting_val}
            )

    def get_player_from_hash(self, user_hash: str) -> Optional[TablePlayer]:
        """Takes in a slack user hash, outputs the expunged object, if any"""
        with self.session_mgr() as session:
            user = session.query(TablePlayer).filter(TablePlayer.slack_user_hash == user_hash).one_or_none()
            if user is not None:
                session.expunge(user)
        return user

    def log_error_to_db(self, e: Exception, error_type: CahErrorType, player_key: int = None,
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
