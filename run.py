#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from cah.settings.config import Production

if __name__ == '__main__':
    Production.build_db_engine()
    from cah.app import create_app

    app = create_app(config_class=Production, props=Production.SECRETS)
    app.run(port=Production.PORT)
