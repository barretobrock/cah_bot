# Cards Against Humanity (CAH) bot
A way to play CAH in Slack

## Info
This is really something I built for personal use. There are credential collection methods that rely on prebuilt routines that might prove specific to only my use case. Should anyone discover this and wish to use it, feel free to contact me and I'll work on adapting this to wider use cases.

## Prerequisites
 - py-package-manager cloned
 - bash enabled, not dash
 ```bash
# Check with
sh --version
# Change with
sudo dpkg-reconfigure dash 
```

## Installation

### Python Script
```bash
cd ~/venvs && python3 -m venv cah_bot
source ~/venvs/cah_bot/bin/activate
cd ~/extras && git clone https://github.com/barretobrock/cah_bot.git
cd cah_bot && make pull
```
### Daemon installation
```bash
# Add service file to system
sudo cp cah.service /lib/systemd/system/
sudo chmod 644 /lib/systemd/system/cah.service
sudo systemctl daemon-reload
sudo systemctl enable cah.service
```
### Postgres database setup
NB! This assumes Postgres 15 is already installed on your server.

Enter postgres with `sudo -u postgres psql`
```postgresql
-- Create user
CREATE USER <user> WITH ENCRYPTED PASSWORD '<pwd>';
-- Create database & schema
CREATE DATABASE <db>;
\c <db>
CREATE SCHEMA <schema>;
-- Grant perms to database
GRANT ALL PRIVILEGES ON DATABASE <db> TO <usr>;
ALTER DATABASE <db> OWNER TO <usr>;
-- Grant create, usage to user for public schema for shared values
GRANT USAGE, CREATE ON SCHEMA public TO <usr>;
```

## Upgrade
```bash
make update
make pull
```

## Run
```bash
python3 run.py
```

## Local Development
As of April 2022, I switched over to [poetry]() to try and better wrangle with ever-changing requirements and a consistently messy setup.py file. Here's the process to rebuild a local development environment (assuming the steps in [Installation](#installation) have already been done):
### Install poetry
I followed the [guide](https://python-poetry.org/docs/#installation) in the poetry docs to install, following the guidelines for using `curl`. I'd recommend to my future self to just install with `pipx` next time, as that seems to do the trick without `curl`ing a remote file and executing :yikes: So:
```bash
# Prereq: sudo apt install pipx
pipx install poetry
# Confirm install
poetry --version
```
### Updating deps
To update, change the deps in `pyproject.toml`, then run `poetry update` to rebuild the lock file and then `poetry install` to reinstall


## Local testing

### Testing with responses
For local testing with Slack responses, get a different terminal window open and initiate `ngrok` in it to test the webhook outside of the live endpoint
Install `ngrok` via snap with `sudo snap install ngrok`.

```bash
ngrok http 5004
```
Then in another window, run the script to get the bot/app running. Don't forget to change the URL in Slack's preferences.

## App Info

### Permissions
#### Events
 - Bot
   - emoji_changed
   - message.channels
   - message.groups
   - message.im
   - pin_added
   - pin_removed
   - reaction_added
   - user_change
 - User
   - None, ATM
#### OAuth Scopes
 - Bot
   - channels.history
   - *channels.join
   - channels.read
   - chat.write
   - commands (slash)
   - emoji.read
   - files.write
   - groups.history
   - groups.read
   - im.history
   - im.read
   - im.write
   - *incoming-webhook (CURL-based notifications)
   - mpim.read
   - pins.read
   - reactions.read
   - reactions.write
   - users.read
 - User
   - search.read
