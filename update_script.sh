#!/usr/bin/env bash
#/      --update_script.sh--
#/  Pulls changes from remote master and then updates the local python package
#/
#/  Usage: update_script.sh [options]
#/
#/  Options
#/      -s|--skip-deps                      Skips update of dependencies.
#/      -v|--version                        Prints script name & version.
#/

# DEFAULT VARIABLES
# ------------------------------------------
NAME="Repo Update Script"
VERSION="0.0.1"
SKIP_DEPS=0

# Import common variables / functions
source ./common.sh

# REPO-SPECIFIC VARIABLES
# ------------------------------------------
REPO=cah_bot
GIT_URL=git+https://github.com/barretobrock/${REPO}.git#egg=${REPO}
# DIRECTORY
REPO_DIR=${HOME}/extras/${REPO}

NODEPS_FLAG=''
if [[ "${SKIP_DEPS}" == "1" ]];
then
    echo "Not pip installing dependencies"
    NODEPS_FLAG="--no-deps"
fi

# GIT PULL
# ------------------------------------------
announce_section "Pulling update from git repo"
# TODO see if I can check if master is up to date before issuing command. If it is, don't pull
(cd ${REPO_DIR} && git pull origin master)

# PY PACKAGE UPDATE
# ------------------------------------------
# Then update the python package locally
announce_section "Beginning update of ${REPO}"
# TODO check if installed, then upgrade if so
python3 -m pip install ${GIT_URL} --upgrade ${NODEPS_FLAG}

announce_section "Process completed"
