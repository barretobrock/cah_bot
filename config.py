"""Sample config file for package"""
import os


# ==============================================================================
# These are things that likely should be changed before installation
REPO_NAME = 'cah_bot'   # Repo
VENV_NAME = 'cah_bot'        # Virtual environment
MAIN_BRANCH = 'master'      # The primary branch of the repo
# Description of the repo
DESC = 'A slackbot for playing Cards Against Humanity on Slack.'
# Dependencies this package has on any of my other projects.
#   This text gets appended to the placeholder in GIT_DEP_URL below
MY_DEPS = ['slacktools', 'kavalkilu', 'easylogger']

# ==============================================================================
# These are things that probably won't need to be changed much.
#   The 'changy' parts should all be above.
URL_TEMPLATE = 'https://github.com/barretobrock'
URL = f'{URL_TEMPLATE}/{REPO_NAME}'
GIT_URL = f'git+{URL}.git#egg={REPO_NAME}'
VENV_PATH = f'${{HOME}}/venvs/{VENV_NAME}/bin/python3'
DEP_TEMPLATE = f'git+{URL_TEMPLATE}/{{dep}}.git#egg={{dep}}'
DEP_LINKS = [DEP_TEMPLATE.format(dep=x) for x in MY_DEPS]

# ==============================================================================
# This is passed directly to setup(). Make sure the things added here are args that setup() accepts
config_dict = {
    'name': REPO_NAME,
    'description': DESC,
    'license': 'MIT',
    'author': 'Barret Obrock',
    'author_email': 'bobrock@tuta.io',
    'url': URL,
    'dependency_links': DEP_LINKS,
}

if __name__ == '__main__':
    # If this file is run directly, select variables will be placed
    #   in a file to be easily read into a bash script.
    parent_dir = os.path.dirname(__file__)
    # NOTE: The key value will be the variable name in the bash script
    store_these = {
        'REPO_NAME': REPO_NAME,
        'REPO_DIR': os.path.abspath(parent_dir).replace(os.path.expanduser('~'), '${HOME}'),
        'GIT_URL': GIT_URL,
        'VENV_PATH': VENV_PATH,
        'DEP_LINKS': DEP_LINKS,
        'MAIN_BRANCH': MAIN_BRANCH,
    }

    fpath = os.path.join(parent_dir, '_auto_config.sh')
    with open(fpath, 'w') as f:
        f.write('# **This is an automatically-constructed file. See config.py for the source.**\n\n')
        for k, v in store_these.items():
            write_str = ''
            if isinstance(v, list):
                # Add line breaks/tabs to strong
                line_str = ''.join([f'\n\t"{x}"' for x in v])
                write_str += f'{k}=({line_str}\n)'
            else:
                write_str += f'{k}="{v}"'
            f.write(f'{write_str}\n')
