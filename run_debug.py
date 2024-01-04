#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from cah.settings.config import Development

if __name__ == '__main__':
    Development().build_db_engine()
    from cah.app import create_app

    app = create_app(config_class=Development, props=Development.SECRETS)
    app.run(port=Development.PORT, use_reloader=Development.USE_RELOADER)
