# Movie Bot Relay

A Telegram bot that relays movie queries to a third-party movie info bot via a userbot bridge.

## Setup
1. Create a `.env` file based on `.env.example`.
2. Install requirements: `pip install -r requirements.txt`.
3. Run `python auth_userbot.py` to authenticate the MTProto userbot.
4. Run `python bot.py` to start the bot.
