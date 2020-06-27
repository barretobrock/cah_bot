#!/usr/bin/env bash
# Calls the update_script file at whatever path the py-package-manager repo is in
PPM_PATH=${HOME}/extras/py-package-manager/update_script.sh

ADDL="${@}" # Option for passing additional commands onwards
sh ${PPM_PATH} --config $(pwd)/config.yaml ${ADDL}
