#!/usr/bin/env bash
#/      --update_script.sh--
#/  Pulls changes from remote main branch and then updates the local python package
#/
#/  Usage: update_script.sh [options]
#/
#/  Options
#/      -s|--skip-deps                      Skips update of dependencies.
#/      -v|--version                        Prints script name & version.
#/

# Calls the update_script file at whatever path the py-package-manager repo is in
PPM_PATH=../py-package-manager/update_script.sh

if [[ ! -z "${PPM_PATH}" ]]
then
  ADDL="${@}" # Option for passing additional commands onwards
  sh ${PPM_PATH} --config ./config.py ${ADDL}
else
  echo -e "The py-package-manager repo is not in the expected path: ${PPM_PATH}\nAborting process..." && exit 1
fi
