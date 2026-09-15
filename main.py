import os
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env tf u doing man")


class JaggBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content == "!ping":
            await message.channel.send("Pong!")


bot = JaggBot()
bot.run(TOKEN)

