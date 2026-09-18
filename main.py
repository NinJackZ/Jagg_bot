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
    1458098880892895374: "ohtobii",
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

async def get_faceit_history(player_id):
    url = f"https://open.faceit.com/data/v4/players/{player_id}/history"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    params = {
        "game": "cs2",
        "limit": 5
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            params=params
        ) as response:

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

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers
        ) as response:

            if response.status != 200:
                print(
                    f"FACEIT match stats API error: "
                    f"{response.status}"
                )
                return None

            return await response.json()

async def get_faceit_recent_performance(player_id, limit=5):
    history = await get_faceit_history(player_id)

    if not history or not history.get("items"):
        return None

    matches = history["items"][:limit]

    results = []

    for match in matches:
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

        try:
            kd = float(stats_data.get("K/D Ratio", 0))
        except (ValueError, TypeError):
            kd = 0

        try:
            mvps = int(stats_data.get("MVPs", 0))
        except (ValueError, TypeError):
            mvps = 0

        try:
            score = float(stats_data.get("Score", 0))
        except (ValueError, TypeError):
            score = 0

        result = "Unknown"

        player_result = stats_data.get("Result")

        if player_result == "1":
            result = "Win"
        elif player_result == "0":
            result = "Loss"

        results.append({
            "match_id": match_id,
            "kills": kills,
            "deaths": deaths,
            "kd": kd,
            "mvps": mvps,
            "score": score,
            "result": result
        })

    if not results:
        return None

    total_kills = sum(match["kills"] for match in results)
    total_deaths = sum(match["deaths"] for match in results)

    average_kills = total_kills / len(results)
    average_deaths = total_deaths / len(results)
    average_kd = sum(match["kd"] for match in results) / len(results)
    average_mvps = sum(match["mvps"] for match in results ) / len(results)
    average_score = sum(match["score"] for match in results) / len(results)

    wins = sum(1 for match in results if match["result"] == "Win")
    losses = sum(1 for match in results if match["result"] == "Loss")
    win_rate = (wins / len(results)) * 100
    
    return {
        "matches": results,
        "match_count": len(results),
        "wins": wins,
        "losses": losses,
        "average_mvps": average_mvps,
        "win_rate": win_rate,
        "average_kills": average_kills,
        "average_deaths": average_deaths,
        "average_kd": average_kd,
        "average_score": average_score,
    }

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

    # Sort by average K/D
    leaderboard.sort(
        key=lambda player: player["average_kd"],
        reverse=True
    )

    lines = []

    header = (
        f"{'Rank':<5}"
        f"{'Player':<16}"
        f"{'MVPs':<8}"
        f"{'Kills':<9}"
        f"{'Deaths':<9}"
        f"{'K/D':<8}"
        f"{'Win %':<8}"
    )

    separator = "─" * len(header)

    lines.append(header)
    lines.append(separator)

    for index, player in enumerate(leaderboard, start=1):

        player_name = player["name"][:15]

        # Rank symbols for the top 3
        if index == 1:
            rank = "#1"
        elif index == 2:
            rank = "#2"
        elif index == 3:
            rank = "#3"
        else:
            rank = f"#{index}"

        lines.append(
            f"{rank:<5}"
            f"{player_name:<16}"
            f"{player['average_mvps']:<8.1f}"
            f"{player['average_kills']:<9.1f}"
            f"{player['average_deaths']:<9.1f}"
            f"{player['average_kd']:<8.2f}"
            f"{player['win_rate']:<8.0f}"
        )

    table = "\n".join(lines)

    # Best guy
    best = max(
        leaderboard,
        key=lambda player: player["average_kd"]
    )

    best_mention = f"<@{best['discord_id']}>"

    best_message = (
        f"**{best_mention} is the current GOAT**\n"
        f"Average K/D: **{best['average_kd']:.2f}** "
        f"over {best['match_count']} games.\n"
        f"Everyone in the server get on your knees and get sucking"
    )

    # Worst guy
    worst = min(
        leaderboard,
        key=lambda player: player["average_kd"]
    )

    worst_mention = f"<@{worst['discord_id']}>"

    roast = (
        f"💀 **{worst_mention} <- This guy fucking blows man.**\n"
        f"Average K/D: **{worst['average_kd']:.2f}** "
        f"over {worst['match_count']} games.\n"
        f"Homie is the worst exedian. Everyone point and laugh."
    )

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

    await interaction.followup.send(embed=embed)

bot.run(TOKEN)