#!/usr/bin/env bash
# ------------------------------------------
# COMMON VARIABLES / FUNCTIONS
# ------------------------------------------
BLUE="\e[34m"
GREEN="\e[32m"
RED="\e[31m"
RESET="\e[0m"

announce_section () {
    # Makes sections easier to see in output
    SECTION_BRK="\n==============================\n"
    SECTION="${1}"
    printf "${BLUE}${SECTION_BRK}${SECTION}${SECTION_BRK}${RESET}"
}

arg_parse() {
    # Parses arguments from command line
    POSITIONAL=()
    while [[ $# -gt 0 ]]
    do
        key="$1"
        case ${key} in
            -s|--skip-deps)
                SKIP_DEPS=1
                shift # past argument
                ;;
            -v|--version)   # Print script name & version
                echo "${NAME} ${VERSION}"
                exit 0
                ;;
            -l|--level)
                LEVEL=${2:-patch}
                shift # past argument
                shift # past value
                ;;
            *)    # unknown option
                POSITIONAL+=("$1") # save it in an array for later
                shift # past argument
                ;;
    esac
    done
    set -- "${POSITIONAL[@]}" # restore positional parameters
    # Check for unknown arguments passed in
    [[ ! -z "${POSITIONAL}" ]] && echo "Unknown args passed: ${POSITIONAL[@]}"
}

# Collect arguments when this is called
arg_parse "$@"
