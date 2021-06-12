#!/usr/bin/env bash
# Calls the update_script file at whatever path the py-package-manager repo is in
PPM_PATH=../py-package-manager/update_script.sh

if [[ ! -z "${PPM_PATH}" ]]
then
  ADDL="${@}" # Option for passing additional commands onwards
  sh ${PPM_PATH} --config ./config.py ${ADDL}
else
  echo -e "The py-package-manager repo is not in the expected path: ${PPM_PATH}\nAborting process..." && exit 1
fi
