import discord
from config import FACEIT_API_KEY, FACEIT_PLAYERS

async def get_faceit_player(bot, username):
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
            print(f"FACEIT API error: {response.status}")
            return None

        return await response.json()


async def get_faceit_history(bot, player_id):
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
            print(f"FACEIT history API error: {response.status}")
            return None

        return await response.json()


async def get_faceit_match_stats(bot, match_id):
    url = f"https://open.faceit.com/data/v4/matches/{match_id}/stats"

    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    async with bot.faceit_session.get(url, headers=headers) as response:
        if response.status != 200:
            print(f"FACEIT match stats API error: {response.status}")
            return None

        return await response.json()


async def get_faceit_recent_performance(bot, player_id, limit=5):
    history = await get_faceit_history(bot, player_id)

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
    total_utility_damage = 0
    total_enemies_flashed = 0
    total_utility_count = 0
    total_utility_successes = 0

    if not history or not history.get("items"):
        return None

    for match in history["items"][:limit]:
        match_id = match.get("match_id")

        if not match_id:
            continue

        stats = await get_faceit_match_stats(bot, match_id)

        if not stats:
            continue

        player_stats = None

        for round_data in stats.get("rounds", []):
            for team in round_data.get("teams", []):
                for member in team.get("players", []):
                    if str(member.get("player_id")) == str(player_id):
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

        try:
            utility_damage = int(stats_data.get("Utility Damage", 0))
        except (ValueError, TypeError):
            utility_damage = 0

        total_utility_damage += utility_damage

        try:
            enemies_flashed = int(stats_data.get("Enemies Flashed", 0))
        except (ValueError, TypeError):
            enemies_flashed = 0

        total_enemies_flashed += enemies_flashed

        try:
            utility_count = int(stats_data.get("Utility Count", 0))
        except (ValueError, TypeError):
            utility_count = 0

        total_utility_count += utility_count

        try:
            utility_successes = int(stats_data.get("Utility Successes", 0))
        except (ValueError, TypeError):
            utility_successes = 0

        total_utility_successes += utility_successes

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

    entry_success_rate = (
        total_entry_wins / total_entry_count
        if total_entry_count > 0 else 0
    )

    completed_matches = wins + losses

    utility_damage_per_match = total_utility_damage / match_count
    enemies_flashed_per_match = total_enemies_flashed / match_count

    utility_success_rate = (
        total_utility_successes / total_utility_count
        if total_utility_count > 0 else 0
    )

    win_rate = (
        (wins / completed_matches) * 100
        if completed_matches > 0 else 0
    )

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
        "util_dmg_per_match": utility_damage_per_match,
        "enemies_flashed_per_match": enemies_flashed_per_match,
        "utility_success_rate": utility_success_rate,
    }


def get_support_leaderboard(leaderboard):
    if not leaderboard:
        return []

    stats = [
        "enemies_flashed_per_match",
        "util_dmg_per_match",
        "utility_success_rate",
    ]

    for stat in stats:
        values = [player[stat] for player in leaderboard]

        minimum = min(values)
        maximum = max(values)

        for player in leaderboard:
            if maximum == minimum:
                player[f"{stat}_score"] = 1
            else:
                player[f"{stat}_score"] = (
                    (player[stat] - minimum)
                    / (maximum - minimum)
                )

    for player in leaderboard:
        player["support_score"] = (
            player["enemies_flashed_per_match_score"] * 0.38
            + player["util_dmg_per_match_score"] * 0.42
            + player["utility_success_rate_score"] * 0.20
        )

    return sorted(
        leaderboard,
        key=lambda player: player["support_score"],
        reverse=True
    )


async def faceit_leaderboard(interaction: discord.Interaction, bot):
    await interaction.response.defer()

    leaderboard = []

    for discord_user_id, faceit_username in FACEIT_PLAYERS.items():
        player = await get_faceit_player(bot, faceit_username)

        if not player:
            continue

        player_id = player.get("player_id")

        if not player_id:
            continue

        performance = await get_faceit_recent_performance(
            bot,
            player_id,
            limit=5,
        )

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
        await interaction.followup.send("No faceit data man.")
        return

    stats = [
        "kd", "kr", "adr", "win_rate",
        "entry_success_rate", "total_clutches"
    ]

    for stat in stats:
        values = [player[stat] for player in leaderboard]

        minimum = min(values)
        maximum = max(values)

        for player in leaderboard:
            if maximum == minimum:
                player[f"{stat}_score"] = 1
            else:
                player[f"{stat}_score"] = (
                    (player[stat] - minimum) / (maximum - minimum)
                )

    for player in leaderboard:
        player["overall_score"] = (
            player["kd_score"]
            + player["kr_score"]
            + player["adr_score"]
            + player["win_rate_score"]
            + player["entry_success_rate_score"]
            + player["total_clutches_score"]
        ) / 6

    leaderboard.sort(
        key=lambda player: player["overall_score"],
        reverse=True,
    )

    lines = []

    header = (
        f"{'Rank':<6}"
        f"{'Player':<14}"
        f"{'K/D':<7}"
        f"{'K/R':<7}"
        f"{'ADR':<8}"
        f"{'Win %':<7}"
        f"{'Entry %':<8}"
        f"{'Clutch':<7}"
    )

    lines.extend([header, "─" * len(header)])

    for index, player in enumerate(leaderboard, start=1):
        if player["discord_id"] == 235072661607284736:
            rank = "🥷🏻"
        elif index == 1:
            rank = "🫅🏻"
        elif index == 2:
            rank = "👨🏻‍🚀"
        elif index == 3:
            rank = "🕴"
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

    best = max(leaderboard, key=lambda player: player["overall_score"])
    best_mention = f"<@{best['discord_id']}>"

    best_message = (
        f"**{best_mention} <- current GOAT**\n"
        f"K/D: **{best['kd']:.2f}** over {best['match_count']} games.\n"
        "Everyone in the server get on your knees and get sucking"
    )

    worst = min(leaderboard, key=lambda player: player["overall_score"])
    worst_mention = f"<@{worst['discord_id']}>"

    roast = (
        f"💀 **{worst_mention} <- This guy fucking blows man.**\n"
        f"K/D: **{worst['kd']:.2f}** over {worst['match_count']} games.\n"
        "Homie is the worst exedian. Everyone point and laugh."
    )

    support_leaderboard = get_support_leaderboard(leaderboard)
    support_lines = []
    support_header = (
        f"{'Rank':<6}"
        f"{'Player':<14}"
        f"{'Flashes':<10}"
        f"{'Util Dmg':<11}"
        f"{'Util %':<9}"
        f"{'Score':<8}"
    )

    support_lines.extend([support_header, "─" * len(support_header)])

    for index, player in enumerate(support_leaderboard, start=1):
        if index == 1:
            rank = "🤯"
        elif index == 2:
            rank = "💣"
        elif index == 3:
            rank = "🧨"
        else:
            rank = f"#{index}"

        support_lines.append(
            f"{rank:<6}"
            f"{player['name']:<14}"
            f"{player['enemies_flashed_per_match']:<10.1f}"
            f"{player['util_dmg_per_match']:<11.1f}"
            f"{player['utility_success_rate'] * 100:<9.1f}"
            f"{player['support_score']:<8.3f}"
        )

    support_table = "\n".join(support_lines)

    best_support = max(
        support_leaderboard,
        key=lambda player: player["support_score"]
    )

    best_support_message = (
        f"**<@{best_support['discord_id']}> <- Lineups are working.**\n"
        f"Enemies flashed (per match): **{best_support['enemies_flashed_per_match']:.1f}**\n"
        f"Utility Damage (per match): **{best_support['util_dmg_per_match']:.1f}**\n"
        f"Utility Success Rate: **{best_support['utility_success_rate']:.1%}**\n"
        "Please teach the rest how to use util."
    )

    worst_support = min(
        support_leaderboard,
        key=lambda player: player["support_score"]
    )

    worst_support_message = (
        f"**<@{worst_support['discord_id']}> <- Can't even throw a grenade right.**\n"
        f"Enemies flashed (per match): **{worst_support['enemies_flashed_per_match']:.1f}**\n"
        f"Utility Damage (per match): **{worst_support['util_dmg_per_match']:.1f}**\n"
        f"Utility Success Rate: **{worst_support['utility_success_rate']:.1%}**\n"
        "Making the exedite eyesight worse with each game played."
    )

    embed = discord.Embed(
        title="Exedite FACEIT Leaderboard",
        description=f"```text\n{table}\n```",
        color=discord.Color.gold()
    )

    embed.add_field(name="Current GOAT", value=best_message, inline=False)
    embed.add_field(name="Server Shitter", value=roast, inline=False)

    embed.add_field(
        name="Support Leaderboard",
        value=f"```text\n{support_table}\n```",
        inline=False
    )

    embed.add_field(name="Grenade Geezer", value=best_support_message, inline=False)
    embed.add_field(name="Utility Unloader", value=worst_support_message, inline=False)

    await interaction.followup.send(embed=embed)

    yas_last = leaderboard[-1]

    if yas_last["discord_id"] == 258339524579426304:
        from config import BASE_DIR

        gif_path = BASE_DIR / "assets" / "Yas.gif"

        if gif_path.exists():
            await interaction.followup.send(file=discord.File(gif_path))