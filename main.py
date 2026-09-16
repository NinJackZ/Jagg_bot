import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import voice_recv
from faster_whisper import WhisperModel
import discord.ext.voice_recv as voice_recv
import wave, asyncio, io

load_dotenv()

# Change based on server id
GUILD_IDS = [
    1549815539520774144,
    236828540975185921,
]

# Initialize the Whisper model
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

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
                    language="en"
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

                if matched_slur:
                    print(
                        f"Blocked word detected from {user_id}: "
                        f"{matched_slur}"
                    )

                    # Find the Discord member in the guild
                    for guild in bot.guilds:
                        member = guild.get_member(user_id)

                        if member:
                            # Announce in the channel
                            channel = member.voice.channel if member.voice else None

                            if channel:
                                await channel.send(
                                    f"{member.mention} has been removed from "
                                    f"voice chat for using a the word '{matched_slur}'"
                                )

                                # Disconnect them from voice
                                await member.move_to(None)

                            break

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
# Link command to link a Discord account to a FACEIT account
# @bot.tree.command(name="link", description="Link your Discord account to a FACEIT account")
# async def link(interaction: discord.Interaction, username: str):
#     await interaction.response.send_message(f"FACEIT username received: `{username}`")

bot.run(TOKEN)