#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from cah.app import create_app
from cah.settings.config import Production

if __name__ == '__main__':
    app = create_app(config_class=Production)
    app.run(port=Production.PORT)
