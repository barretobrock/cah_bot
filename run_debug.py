#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
os.environ['CAH_DEBUG'] = "1"
from cah.app import app


@app.route('/cah')
def index():
    return 'CAH'


if __name__ == '__main__':
    app.run(port=5004)


