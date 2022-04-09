#!/usr/bin/env bash
#/ ppmgr.sh - The client file for PyPackageManager
#/      This script handles sending off the commands for PPM to the local ppm_main script.


# PROJECT-SPECIFIC VARIABLES
# -------------------------------------
# These you'll likely need to change
GIT_GROUP="barretobrock"
PROJECT="cah_bot"
PY_LIB_NAME="cah"
VENV_NAME="cah_bot"
MAIN_BRANCH="master"
# -------------------------------------

# Command to use (bump|pull|push)
#   bump - bump version, update CHANGELOG
#   pull - pull down changes & reinstall
#   push - push changes to remote & tag
CMD=${1:pull}
# Get the level to increment on (major|minor|patch)
LEVEL=${2:-patch}

# Calls the push_changes file at whatever path the py-package-manager repo is in
PPM_PATH=../py-package-manager/ppm_main.sh

echo "Received ${CMD} and ${LEVEL}"

if [[ -s "${PPM_PATH}" ]]
then
    sh ${PPM_PATH} -d --level ${LEVEL} --project ${PROJECT} --cmd ${CMD} --lib ${PY_LIB_NAME} --venv ${VENV_NAME} --main-branch ${MAIN_BRANCH}
else
    echo "The py-package-manager repo is not in the expected path: ${PPM_PATH}\nAborting process..." && exit 1
fi