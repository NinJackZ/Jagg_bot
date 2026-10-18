import os
from pathlib import Path
from dotenv import load_dotenv

# Project root directory
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the project root
load_dotenv(BASE_DIR / ".env")

# Discord and FACEIT credentials
TOKEN = os.getenv("DISCORD_TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

# Discord server IDs
GUILD_IDS = [
    int(guild_id.strip())
    for guild_id in os.getenv("GUILD_IDS", "").split(",")
    if guild_id.strip()
]

# FACEIT usernames linked to Discord user IDs
FACEIT_PLAYERS = {}

for player in os.getenv("FACEIT_PLAYERS", "").split(","):
    player = player.strip()

    if not player:
        continue

    discord_id, faceit_username = player.split(":", 1)

    FACEIT_PLAYERS[int(discord_id)] = faceit_username.strip()