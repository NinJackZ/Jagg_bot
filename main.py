import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import voice_recv
import logging, asyncio, aiohttp
from faceit import faceit_leaderboard
from moderation import on_voice_packet, transcribe_voice_loop, moderate_message

logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)

load_dotenv()

# Change based on server id
GUILD_IDS = [
    int(guild_id.strip())
    for guild_id in os.getenv("GUILD_IDS", "").split(",")
    if guild_id.strip()
]

# Map Faceit User to discord user
FACEIT_PLAYERS = {}

for player in os.getenv("FACEIT_PLAYERS", "").split(","):
    player = player.strip()

    if not player:
        continue

    discord_id, faceit_username = player.split(":", 1)

    FACEIT_PLAYERS[int(discord_id)] = faceit_username

TOKEN = os.getenv("DISCORD_TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env tf u doing man")

if not FACEIT_API_KEY:
    raise RuntimeError("Dude where tf is ur faceit api key")

if not GUILD_IDS:
    raise RuntimeError("GUILD_IDS is not set in .env")

if not FACEIT_PLAYERS:
    raise RuntimeError("FACEIT_PLAYERS is not set in .env")

class JaggBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def on_ready(self):
        # User serverid or guildid to sync commands to a specific server
        for guild_id in GUILD_IDS:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)

            if not hasattr(bot, "voice_transcription_task"):
                bot.voice_transcription_task = asyncio.create_task(
                    transcribe_voice_loop(bot)
                )

            print(f"Logged in as {self.user} (ID: {self.user.id})")
            print(f"Synced {len(synced)} command(s) to server {guild_id}")

    async def on_message(self, message):
        await moderate_message(message)
        await self.process_commands(message)

bot = JaggBot()

# Define slash commands
# Ping command to check if the bot is online
@bot.tree.command(name="ping", description="Check if the bot is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# Join command to join the user's current voice channel
@bot.tree.command(name="join", description="Join your current voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message(
            "You need to be in a voice channel first.",
            ephemeral=True
        )
        return

    channel = interaction.user.voice.channel

    if interaction.guild.voice_client:
        await interaction.response.send_message(
            "I'm already connected to a voice channel.",
            ephemeral=True
        )
        return

    voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
    voice_client.listen(voice_recv.BasicSink(on_voice_packet))

    await interaction.response.send_message(
        f"Joined **{channel.name}**."
    )

# Faceit leaderboard command
@bot.tree.command( name="faceit", description="Show each Faceit Exedian stats on their last 5 matches" )
async def faceit(interaction: discord.Interaction):
    await faceit_leaderboard(interaction, bot)

bot.run(TOKEN)