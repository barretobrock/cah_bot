import os

from .config import (
    Development,
    Production,
)

config_space = os.getenv('CAH_ENV', 'DEVELOPMENT')
if config_space == 'DEVELOPMENT':
    auto_config = Development
elif config_space == 'PRODUCTION':
    auto_config = Production
