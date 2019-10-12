#!/usr/bin/env bash
# Run this script after committing
# Example use
# Patch
# > sh push_changes.sh
# Minor update
# > sh push_changes.sh minor

LEVEL=${1:-patch}

# Terminal colors
BLUE="\e[34m"
RESET="\e[0m"

# Get highest tag number
VERSION=`git describe --abbrev=0 --tags`

# Replace . with space so can split into an array
VERSION_BITS=(${VERSION//./ })

# Get number parts and increase last one by 1
VNUM1=${VERSION_BITS[0]}
VNUM2=${VERSION_BITS[1]}
VNUM3=${VERSION_BITS[2]}

if [[ "${LEVEL}" == "patch" ]];
then
    VNUM3=$((VNUM3+1))
elif [[ "${LEVEL}" == "minor" ]];
then
    VNUM2=$((VNUM2+1))
    VNUM3=0
elif [[ "${LEVEL}" == "major" ]];
then
    VNUM1=$((VNUM1+1))
    VNUM2=0
    VNUM3=0
fi


#create new tag
NEW_TAG="${VNUM1}.${VNUM2}.${VNUM3}"

CONFIRM="Updating ${BLUE}${VERSION}${RESET} to ${BLUE}${NEW_TAG}${RESET}. Enter to continue. CTRL+C to halt."
read -p "$( echo -e ${CONFIRM})"

# Get current hash and see if it already has a tag
GIT_COMMIT=`git rev-parse HEAD`
NEEDS_TAG=`git describe --contains ${GIT_COMMIT}`

# Only tag if no tag already (would be better if the git describe command above could have a silent option)
if [[ -z "$NEEDS_TAG" ]]; then
    echo "Tagged with ${NEW_TAG} (Ignoring fatal:cannot describe - this means commit is untagged) "
    git tag ${NEW_TAG}
    git push --follow-tags
else
    echo "Already a tag on this commit"
fi

