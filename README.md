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
```bash
cd ~/venvs && python3 -m venv cah_bot
source ~/venvs/cah_bot/bin/activate
cd ~/extras && git clone https://github.com/barretobrock/cah_bot.git
cd cah_bot && sh update_script.sh

# Add service file to system
sudo cp cah.service /lib/systemd/system/
sudo chmod 644 /lib/systemd/system/cah.service
sudo systemctl daemon-reload
sudo systemctl enable cah.service
```

## Upgrade
```bash
sh update_script.sh
```

## Run
```bash
python3 run.py
```





