#!/usr/bin/env bash
# Calls the push_changes file at whatever path the py-package-manager repo is in
PPM_PATH=${HOME}/extras/py-package-manager/push_changes.sh

ADDL="${@}" # Option for passing additional commands onwards
sh ${PPM_PATH} --config $(pwd)/config.yaml ${ADDL}
