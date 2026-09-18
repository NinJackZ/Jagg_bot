import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import voice_recv
from faster_whisper import WhisperModel
import discord.ext.voice_recv as voice_recv
import wave, asyncio, io, logging, aiohttp

logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)

load_dotenv()

# Change based on server id
GUILD_IDS = [
    1549815539520774144, # Jack Test server
    236828540975185921, # Exedite
]

# Map Faceit User to discord user
FACEIT_PLAYERS = {
    235072661607284736: "Tongetoon",
    255268597386051584: "DragonDAI",
    258339524579426304: "The_Pharao",
    189073530996916226: "Adreaf",
    443046560658620436: "_SpooN_",
    594833314691678209: "SpahooN",
    577778649579782144: "IBADDDD",
}

# Initialize the Whisper model
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")

TOKEN = os.getenv("DISCORD_TOKEN")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env tf u doing man")

if not FACEIT_API_KEY:
    raise RuntimeError("Dude where tf is ur faceit api key")

# Initilize the bot with a list of slurs
def load_slurs():
    with open("slurs.txt", "r", encoding="utf-8") as f:
        return {
            line.strip().lower() for line in f if line.strip()
        }
    
SLURS = load_slurs()

# Check to receuive audio packets from users in voice channels
voice_audio = {}
voice_audio_locks = {}

def on_voice_packet(user, data):
    if not data.pcm:
        return

    user_id = user.id

    if user_id not in voice_audio:
        voice_audio[user_id] = bytearray()

    voice_audio[user_id].extend(data.pcm)

async def get_faceit_player(username):
    url = "https://open.faceit.com/data/v4/players"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    params = {
        "nickname": username,
        "game": "cs2"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            params=params
        ) as response:

            if response.status != 200:
                print(
                    f"FACEIT API error: "
                    f"{response.status}"
                )
                return None

            return await response.json()

# Helper to transcribe each recieved audio packet
async def transcribe_voice_loop():
    while True:
        await asyncio.sleep(5)

        if not voice_audio:
            continue

        for user_id, audio in list(voice_audio.items()):
            if not audio:
                continue

            # Take the current audio and start a fresh buffer
            audio_chunk = bytes(audio)
            voice_audio[user_id].clear()

            try:
                # Create an in-memory wav file
                wav_buffer = io.BytesIO()

                with wave.open(wav_buffer, "wb") as wav_file:
                    wav_file.setnchannels(2)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(48000)
                    wav_file.writeframes(audio_chunk)

                wav_buffer.seek(0)

                # Whisper expects a file-like object or path
                segments, info = whisper_model.transcribe(
                    wav_buffer,
                    language="en",
                    vad_filter=True,
                    condition_on_previous_text=False
                )

                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                ).strip()

                if text:
                    print(
                        f"Transcription from {user_id}: {text}"
                    )

                matched_slur = next(
                    (
                        slur
                        for slur in SLURS
                        if slur in text.lower()
                    ),
                    None
                )

                # if matched_slur:
                #     print(
                #         f"Blocked word detected from {user_id}: "
                #         f"{matched_slur}"
                #     )

                #     # Find the Discord member in the guild
                #     for guild in bot.guilds:
                #         member = guild.get_member(user_id)

                #         if member:
                #             # Announce in the channel
                #             channel = member.voice.channel if member.voice else None

                #             if channel:
                #                 await channel.send(
                #                     f"{member.mention} has been removed from "
                #                     f"voice chat for using the word '{matched_slur}'"
                #                 )

                #                 # Disconnect them from voice
                #                 await member.move_to(None)

                #             break

            except Exception as e:
                print(
                    f"Voice transcription error for {user_id}: {e}"
                )


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
                    transcribe_voice_loop()
                )

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

# Save voice audio to WAV file
@bot.tree.command(name="savevoice", description="Save received voice audio to a WAV file")
async def savevoice(interaction: discord.Interaction):
    global voice_audio

    if not voice_audio:
        await interaction.response.send_message(
            "No voice audio has been received yet.",
            ephemeral=True
        )
        return

    filename = "voice_test.wav"

    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)

        for user_audio in voice_audio.values():
            wav_file.writeframes(user_audio)

    voice_audio.clear()

    await interaction.response.send_message(
        f"Saved received voice audio to `{filename}`."
    )

@bot.tree.command(name="transcribe", description="Transcribe the saved voice recording")
async def transcribe(interaction: discord.Interaction):
    filename = "voice_test.wav"

    try:
        segments, info = whisper_model.transcribe(filename)

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        if not text:
            text = "No speech detected."

        await interaction.response.send_message(
            f"**Transcription:**\n{text}"
        )

    except Exception as e:
        print(f"Transcription error: {e}")

        await interaction.response.send_message(
            "Failed to transcribe the recording.",
            ephemeral=True
        )

@bot.tree.command(name="faceit", description="Show your FACEIT profile")
async def faceit(interaction: discord.Interaction):
    discord_user_id = interaction.user.id

    # Check if this discord user has a faceit account configured
    if discord_user_id not in FACEIT_PLAYERS:
        await interaction.response.send_message(
            "You don't have a FACEIT account configured.",
            ephemeral=True
        )
        return

    faceit_username = FACEIT_PLAYERS[discord_user_id]

    await interaction.response.defer()

    player = await get_faceit_player(faceit_username)

    if not player:
        await interaction.followup.send(
            f"Couldn't find FACEIT player `{faceit_username}`."
        )
        return

    game_data = player.get("games", {}).get("cs2")

    if not game_data:
        await interaction.followup.send(
            f"Found `{player.get('nickname', faceit_username)}`, "
            "but no CS2 data was returned."
        )
        return

    await interaction.followup.send(
        f"🎮 **{player.get('nickname', faceit_username)}**\n"
        f"FACEIT Level: **{game_data.get('skill_level', 'Unknown')}**\n"
        f"Elo: **{game_data.get('faceit_elo', 'Unknown')}**\n"
        f"Region: **{game_data.get('region', 'Unknown')}**"
    )

bot.run(TOKEN)