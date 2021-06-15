#!/usr/bin/env bash
#/      --push_changes.sh--
#/  Pushes a commit to master while also incrementing the version based on
#/      the "level" of changes that have taken place and tagging that onto the commit.
#/
#/  Usage: push_changes.sh [options]
#/
#/  Options
#/      -v|--version                        Prints script name & version.
#/      -l|--level (patch|minor|major)      Sets level of update, to determine version bump (default: patch)
#/

# Calls the push_changes file at whatever path the py-package-manager repo is in
PPM_PATH=../py-package-manager/push_changes.sh

if [[ ! -z "${PPM_PATH}" ]]
then
  ADDL="${@}" # Option for passing additional commands onwards
  sh ${PPM_PATH} --config ./config.py ${ADDL}
else
  echo -e "The py-package-manager repo is not in the expected path: ${PPM_PATH}\nAborting process..." && exit 1
fi
