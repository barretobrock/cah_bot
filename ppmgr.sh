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
# These you might not need to change
PROJECT_DIR="${HOME}/extras/${PROJECT}"
VERSION_FPATH="${PROJECT_DIR}/${PY_LIB_NAME}/__init__.py"
PYPROJECT_TOML_FPATH="${PROJECT_DIR}/pyproject.toml"
CHANGELOG_PATH="${PROJECT_DIR}/CHANGELOG.md"
VENV_PATH="${HOME}/venvs/${VENV_NAME}/bin/python3"
# This is just to turn on/off debug level logging
DEBUG_LOG=1
# -------------------------------------

# Command to use (bump|pull|push)
#   bump - bump version, update CHANGELOG
#   pull - pull down changes & reinstall
#   push - push changes to remote & tag
CMD=${1:update}
# Get the level to increment on (major|minor|patch)
LEVEL=${2:-patch}

# Calls the push_changes file at whatever path the py-package-manager repo is in
PPM_PATH=../py-package-manager/ppm_main.sh

if [[ ! -z "${PPM_PATH}" ]]
then
  ADDL="${@}" # Option for passing additional commands onwards
  sh ${PPM_PATH} ${CMD} ${LEVEL} ${ADDL}
else
  echo -e "The py-package-manager repo is not in the expected path: ${PPM_PATH}\nAborting process..." && exit 1
fi
