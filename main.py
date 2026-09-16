import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Change based on server id
GUILD_IDS = [
    1549815539520774144,
    236828540975185921,
]

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env tf u doing man")


# Initilize the bot with a list of slurs
def load_slurs():
    with open("slurs.txt", "r", encoding="utf-8") as f:
        return {
            line.strip().lower() for line in f if line.strip()
        }
    
SLURS = load_slurs()


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

            print(f"Logged in as {self.user} (ID: {self.user.id})")
            print(f"Synced {len(synced)} command(s) to server {guild_id}")

    async def on_message(self, message):
        if message.author.bot:
            return

        message_content = message.content.lower()

        # Check for slurs in the message content
        matched_slur = next((slur for slur in SLURS if slur in message_content), None)

        if matched_slur:
            print(
                f"Blocked word detected from "
                f"{message.author} in #{message.channel}: {matched_slur}"
            )

            await message.channel.send(f"@everyone Guys get a load of this guy -> {message.author.mention} he said {matched_slur}, what a loser!")

            if message.author.voice:
                await message.author.move_to(None)

bot = JaggBot()

# Define slash commands
# Ping command to check if the bot is online
@bot.tree.command(name="ping", description="Check if the bot is online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# Link command to link a Discord account to a FACEIT account
# @bot.tree.command(name="link", description="Link your Discord account to a FACEIT account")
# async def link(interaction: discord.Interaction, username: str):
#     await interaction.response.send_message(f"FACEIT username received: `{username}`")

bot.run(TOKEN)