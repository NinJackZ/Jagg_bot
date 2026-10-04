import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import voice_recv
from faster_whisper import WhisperModel
import wave, asyncio, io, logging, aiohttp, re, time, scipy.signal
import numpy as np

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

# Initialize the Whisper model
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")

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

# Initilize the bot with a list of slurs
def load_slurs():
    with open("slurs.txt", "r", encoding="utf-8") as f:
        return {
            line.strip().lower() for line in f if line.strip()
        }
    
SLURS = load_slurs()

# Check to receuive audio packets from users in voice channels
voice_audio = {}
voice_last_spoke = {}
transcription_lock = asyncio.Lock()

def on_voice_packet(user, data):
    if user is None or not data.pcm:
        return

    user_id = user.id

    if user_id not in voice_audio:
        voice_audio[user_id] = bytearray()

    voice_audio[user_id].extend(data.pcm)

    # Calculate the volume of this audio packet
    audio_samples = np.frombuffer(data.pcm, dtype=np.int16)

    if audio_samples.size == 0:
        return

    rms = np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2))

    if rms >= 150:
        voice_last_spoke[user_id] = time.monotonic()

async def get_faceit_player(username):
    url = "https://open.faceit.com/data/v4/players"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    params = {
        "nickname": username,
        "game": "cs2"
    }

    async with bot.faceit_session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                print(
                    f"FACEIT API error: "
                    f"{response.status}"
                )
                return None

            return await response.json()

async def get_faceit_history(player_id):
    url = f"https://open.faceit.com/data/v4/players/{player_id}/history"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    params = {
        "game": "cs2",
        "limit": 5
    }

    async with bot.faceit_session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                print(
                    f"FACEIT history API error: "
                    f"{response.status}"
                )
                return None

            return await response.json()

async def get_faceit_match_stats(match_id):
    url = f"https://open.faceit.com/data/v4/matches/{match_id}/stats"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    async with bot.faceit_session.get(url, headers=headers) as response:
            if response.status != 200:
                print(
                    f"FACEIT match stats API error: "
                    f"{response.status}"
                )
                return None

            return await response.json()

async def get_faceit_recent_performance(player_id, limit=5):
    history = await get_faceit_history(player_id)
    total_kills = 0
    total_deaths = 0
    wins = 0
    losses = 0
    total_entry_count = 0
    total_entry_wins = 0
    total_clutches = 0
    total_kr = 0
    total_adr = 0
    match_count = 0

    if not history or not history.get("items"):
        return None

    for match in history["items"][:limit]:
        match_id = match.get("match_id")

        if not match_id:
            continue

        stats = await get_faceit_match_stats(match_id)

        if not stats:
            continue

        player_stats = None

        for round_data in stats.get("rounds", []):
            for team in round_data.get("teams", []):
                for member in team.get("players", []):
                    if member.get("player_id") == player_id:
                        player_stats = member
                        break

                if player_stats:
                    break

            if player_stats:
                break

        if not player_stats:
            continue

        stats_data = player_stats.get("player_stats", {})

        try:
            kills = int(stats_data.get("Kills", 0))
        except (ValueError, TypeError):
            kills = 0

        try:
            deaths = int(stats_data.get("Deaths", 0))
        except (ValueError, TypeError):
            deaths = 0

        total_kills += kills
        total_deaths += deaths

        try:
            kr = float(stats_data.get("K/R Ratio", 0))
        except (ValueError, TypeError):
            kr = 0

        try:
            adr = float(stats_data.get("ADR", 0))
        except (ValueError, TypeError):
            adr = 0

        total_kr += kr
        total_adr += adr
        match_count += 1

        try:
            entry_count = int(stats_data.get("Entry Count", 0))
        except (ValueError, TypeError):
            entry_count = 0

        try:
            entry_wins = int(stats_data.get("Entry Wins", 0))
        except (ValueError, TypeError):
            entry_wins = 0

        total_entry_count += entry_count
        total_entry_wins += entry_wins

        try:
            clutches = int(stats_data.get("Clutch Kills", 0))
        except (ValueError, TypeError):
            clutches = 0

        total_clutches += clutches

        player_result = stats_data.get("Result")

        if player_result == "1":
            wins += 1
        elif player_result == "0":
            losses += 1


    if match_count == 0:
        return None

    kd = total_kills / total_deaths if total_deaths > 0 else 0
    average_kr = total_kr / match_count
    average_adr = total_adr / match_count
    entry_success_rate = (total_entry_wins / total_entry_count if total_entry_count > 0 else 0)
    completed_matches = wins + losses
    win_rate = ((wins / completed_matches) * 100 if completed_matches > 0 else 0)
    
    return {
        "match_count": match_count,
        "wins": wins,
        "losses": losses,
        "kr": average_kr,
        "adr": average_adr,
        "entry_success_rate": entry_success_rate,
        "total_clutches": total_clutches,
        "win_rate": win_rate,
        "kd": kd,
    }

# Helper to calculate best support player
async def get_best_support_player():
    return



# Helper to transcribe each recieved audio packet
async def transcribe_voice_loop():
    while True:
        await asyncio.sleep(0.2)

        if not voice_audio:
            continue

        for user_id, audio in list(voice_audio.items()):
            if not audio:
                continue

            last_spoke = voice_last_spoke.get(user_id)

            if last_spoke is None:
                continue

            silence_duration = time.monotonic() - last_spoke

            # Wait until the user has been silent for 1sec
            if silence_duration < 1.0:
                continue

            # Take the current audio and start a fresh buffer
            audio_chunk = bytes(audio)
            voice_audio[user_id] = bytearray()
            voice_last_spoke.pop(user_id, None)

            audio_samples = np.frombuffer(audio_chunk, dtype=np.int16)

            if audio_samples.size == 0:
                continue

            # Ignore extremely short audio chunks
            duration = audio_samples.size / (48000 * 2)

            if duration < 0.5:
                continue

            rms = np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2))

            if rms < 150:
                continue

            print(
                f"[VOICE] User {user_id} | "
                f"duration={duration:.2f}s | "
                f"rms={rms:.0f}"
            )

            try:
                # Create an in-memory wav file
                audio_samples = np.frombuffer(
                    audio_chunk,
                    dtype=np.int16
                )

                # Make sure we have complete stereo samples
                if audio_samples.size < 2:
                    continue

                if audio_samples.size % 2 != 0:
                    audio_samples = audio_samples[:-1]

                # Discord audio is stereo: split the two channels
                stereo = audio_samples.reshape(-1, 2)

                # Convert stereo to mono
                mono = stereo.mean(axis=1).astype(np.int16)

                # Resample 48 kHz -> 16 kHz
                mono_16k = scipy.signal.resample_poly(mono, 1, 3).astype(np.int16)

                wav_buffer = io.BytesIO()

                with wave.open(wav_buffer, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_file.writeframes(mono_16k.tobytes())

                wav_buffer.seek(0)

                # Whisper expects a file-like object or path
                async with transcription_lock:
                    segments, info = await asyncio.to_thread(
                        whisper_model.transcribe,
                        wav_buffer,
                        language="en",
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 500,
                            "speech_pad_ms": 200,
                            "threshold": 0.6,
                        },
                        condition_on_previous_text=False,
                        temperature=0.0,
                        beam_size=5,
                        no_speech_threshold=0.6,
                    )

                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                ).strip()

                if text:
                    username = f"User {user_id}"

                    for guild in bot.guilds:
                        member = guild.get_member(user_id)

                        if member:
                            username = member.display_name
                            break

                    print(
                        f"Transcription from {username}: {text}"
                    )

                matched_slur = next(( slur for slur in SLURS if re.search( rf"\b{re.escape(slur)}\b", text.lower() ) ), None)

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
                                    f"voice chat for using the word '{matched_slur}'"
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

        await self.process_commands(message)

    async def setup_hook(self):
        self.faceit_session = aiohttp.ClientSession()

    async def close(self):
        if self.faceit_session:
            await self.faceit_session.close()

        await super().close()

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
@bot.tree.command(name="faceit", description="Show each Faceit Exedian stats on their last 5 matches")
async def faceit_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()

    leaderboard = []

    for discord_user_id, faceit_username in FACEIT_PLAYERS.items():

        player = await get_faceit_player(faceit_username)

        if not player:
            continue

        player_id = player.get("player_id")

        if not player_id:
            continue

        performance = await get_faceit_recent_performance(player_id, limit=5)

        if not performance:
            continue

        member = interaction.guild.get_member(discord_user_id)

        if member:
            display_name = member.display_name
        else:
            display_name = faceit_username

        leaderboard.append({
            "discord_id": discord_user_id,
            "name": display_name,
            "faceit_username": faceit_username,
            **performance
        })

    if not leaderboard:
        await interaction.followup.send(
            "No faceit data man."
        )
        return

    # normalise each stat across the leaderboaprd
    stats = [ "kd", "kr", "adr", "win_rate", "entry_success_rate", "total_clutches" ]

    for stat in stats:
        values = [player[stat] for player in leaderboard]

        minimum = min(values)
        maximum = max(values)

        for player in leaderboard:
            if maximum == minimum:
                player[f"{stat}_score"] = 1
            else:
                player[f"{stat}_score"] = ((player[stat] - minimum) / (maximum - minimum))

    # weight each stat
    for player in leaderboard:
        player["overall_score"] = (player["kd_score"] + player["kr_score"] + player["adr_score"] + player["win_rate_score"] + player["entry_success_rate_score"] + player["total_clutches_score"]) / 6

    # sort by overall performance
    leaderboard.sort(key=lambda player: player["overall_score"], reverse=True)

    lines = []

    header = (
        f"{'Rank':<5}"
        f"{'Player':<14}"
        f"{'K/D':<7}"
        f"{'K/R':<7}"
        f"{'ADR':<8}"
        f"{'Win %':<7}"
        f"{'Entry %':<8}"
        f"{'Clutch':<7}"
    )

    separator = "─" * len(header)

    lines.append(header)
    lines.append(separator)

    for index, player in enumerate(leaderboard, start=1):

        player_name = player["name"][:15]

        # Rank symbols for the top 3
        if index == 1:
            rank = "🫅🏻"
        elif index == 2:
            rank = "🥷🏼"
        elif index == 3:
            rank = "🐌"
        else:
            rank = f"#{index}"

        lines.append(
            f"{rank:<5}"
            f"{player['name']:<14}"
            f"{player['kd']:<7.2f}"
            f"{player['kr']:<7.2f}"
            f"{player['adr']:<8.1f}"
            f"{player['win_rate']:<7.0f}"
            f"{player['entry_success_rate'] * 100:<8.0f}"
            f"{player['total_clutches']:<7}"
        )

    table = "\n".join(lines)

    # Best guy
    best = max(
        leaderboard,
        key=lambda player: player["overall_score"]
    )

    best_mention = f"<@{best['discord_id']}>"

    best_message = (
        f"**{best_mention} is the current GOAT**\n"
        f"K/D: **{best['kd']:.2f}** "
        f"over {best['match_count']} games.\n"
        f"Everyone in the server get on your knees and get sucking"
    )

    # Worst guy
    worst = min(
        leaderboard,
        key=lambda player: player["overall_score"]
    )

    worst_mention = f"<@{worst['discord_id']}>"

    roast = (
        f"💀 **{worst_mention} <- This guy fucking blows man.**\n"
        f"K/D: **{worst['kd']:.2f}** "
        f"over {worst['match_count']} games.\n"
        f"Homie is the worst exedian. Everyone point and laugh."
    )

    # Best support


    embed = discord.Embed(
        title="Exedite FACEIT Leaderboard",
        description=(
            f"```text\n{table}\n```"
        ),
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Current GOAT",
        value=best_message,
        inline=False
    )

    embed.add_field(
        name="Server Shitter",
        value=roast,
        inline=False
    )

    # embed.add_field(
    #     name="Grenade Geezer",
    #     value='',
    #     inline=False
    # )

    await interaction.followup.send(embed=embed)

bot.run(TOKEN)