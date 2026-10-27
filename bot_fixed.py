
import os
import json
import requests
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

# ==================================================
# РќРђРЎРўР РћР™РљР
# ==================================================

TOKEN = os.getenv("DISCORD_TOKEN")
WEBSITE_SYNC_URL = os.getenv("WEBSITE_SYNC_URL", "").rstrip("/")
WEBSITE_SYNC_SECRET = os.getenv("WEBSITE_SYNC_SECRET", "")

GUILD_ID = 1564674095193530468
TESTER_ROLE_ID = 1564689801322438656

QUEUE_CHANNEL_NAME = "🛑очередь"

RANKS_FILE = "ranks.json"
TEAMS_FILE = "teams.json"
QUEUE_FILE = "queue.json"

TIER_ROLE_IDS = {
    "LT5": 1564697151995514992,
    "HT5": 1564697336666525877,
    "LT4": 1564697439959646380,
    "HT4": 1564697541793022104,
    "LT3": 1564697636492288050,
    "HT3": 1564697730415198371,
    "LT2": 1564697834941579365,
    "HT2": 1564698050658701324,
    "LT1": 1564698166039941181,
    "HT1": 1564698274663895140,
}

TIER_ORDER = [
    "LT5", "HT5",
    "LT4", "HT4",
    "LT3", "HT3",
    "LT2", "HT2",
    "LT1", "HT1",
]

TIER_CHOICES = [
    app_commands.Choice(name=tier, value=tier)
    for tier in TIER_ORDER
]

# ==================================================
# РЎРћР—Р”РђРќРР• Р‘РћРўРђ
# ==================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==================================================
# JSON: РЎРћРҐР РђРќР•РќРР• Р Р—РђР“Р РЈР—РљРђ
# ==================================================

def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, OSError):
        return {}


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


ranks_data = load_json(RANKS_FILE)
teams_data = load_json(TEAMS_FILE)
PLAYER_NAMES_FILE = "player_names.json"
player_names_data = load_json(PLAYER_NAMES_FILE)
# ==================================================
# РЎРРќРҐР РћРќРР—РђР¦РРЇ РЎ РЎРђР™РўРћРњ
# ==================================================

def clean_empty_team_pairs():
    """Удаляет пары, если у обоих игроков отсутствуют Minecraft-ники."""
    changed = False
    processed = set()

    for key, team in list(teams_data.items()):
        if not isinstance(team, dict):
            continue

        players = team.get("players")
        if isinstance(players, list) and len(players) == 2:
            pair = tuple(sorted(str(pid) for pid in players))
            if pair in processed:
                continue
            processed.add(pair)

            if not any(str(player_names_data.get(pid, "")).strip() for pid in pair):
                teams_data.pop(key, None)
                for pid, other in ((pair[0], pair[1]), (pair[1], pair[0])):
                    entry = teams_data.get(pid)
                    if isinstance(entry, dict) and str(entry.get("teammate")) == other:
                        teams_data.pop(pid, None)
                changed = True

        elif key.isdigit() and team.get("teammate") is not None:
            pair = tuple(sorted((str(key), str(team["teammate"]))))
            if pair in processed:
                continue
            processed.add(pair)

            if not any(str(player_names_data.get(pid, "")).strip() for pid in pair):
                for pid, other in ((pair[0], pair[1]), (pair[1], pair[0])):
                    entry = teams_data.get(pid)
                    if isinstance(entry, dict) and str(entry.get("teammate")) == other:
                        teams_data.pop(pid, None)
                        changed = True
                teams_data.pop("_".join(pair), None)

    if changed:
        save_json(TEAMS_FILE, teams_data)


def sync_rankings_to_website():
    """Очищает пустые пары и синхронизирует рейтинги с сайтом."""
    clean_empty_team_pairs()

    if not WEBSITE_SYNC_URL or not WEBSITE_SYNC_SECRET:
        print("[Website sync] Не заданы WEBSITE_SYNC_URL или WEBSITE_SYNC_SECRET.")
        return

    try:
        response = requests.post(
            f"{WEBSITE_SYNC_URL}/api/sync",
            json={
                "ranks": ranks_data,
                "teams": teams_data,
                "player_names": player_names_data,
            },
            headers={"Authorization": f"Bearer {WEBSITE_SYNC_SECRET}"},
            timeout=15,
        )
        response.raise_for_status()
        print("[Website sync] Данные отправлены на сайт!")
    except requests.RequestException as error:
        print(f"[Website sync] Ошибка синхронизации: {error}")


queue_data = {
    "open": False,
    "channel_id": None,
    "message_id": None,
    "teams": []
}

saved_queue = load_json(QUEUE_FILE)
queue_data.update(saved_queue)

if not isinstance(queue_data.get("teams"), list):
    queue_data["teams"] = []

if not isinstance(queue_data.get("open"), bool):
    queue_data["open"] = False


def save_queue():
    save_json(QUEUE_FILE, queue_data)


# ==================================================
# РџР РћР’Р•Р РљРђ РџР РђР’ РўР•РЎРўР•Р Рђ
# ==================================================

def is_tester(member):
    if not isinstance(member, discord.Member):
        return False

    return any(role.id == TESTER_ROLE_ID for role in member.roles)


def tester_only():
    async def predicate(interaction: discord.Interaction):
        if not is_tester(interaction.user):
            raise app_commands.CheckFailure(
                "Р­С‚Р° РєРѕРјР°РЅРґР° РґРѕСЃС‚СѓРїРЅР° С‚РѕР»СЊРєРѕ С‚РµСЃС‚РµСЂР°Рј."
            )
        return True

    return app_commands.check(predicate)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CheckFailure):
        message = str(error) or "РЈ С‚РµР±СЏ РЅРµС‚ РїСЂР°РІ РЅР° СЌС‚Сѓ РєРѕРјР°РЅРґСѓ."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return

    print(f"РћС€РёР±РєР° РєРѕРјР°РЅРґС‹: {error}")
    message = "РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР° РїСЂРё РІС‹РїРѕР»РЅРµРЅРёРё РєРѕРјР°РЅРґС‹."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ==================================================
# РћР§Р•Р Р•Р”Р¬: РћР‘РќРћР’Р›Р•РќРР• РЎРћРћР‘Р©Р•РќРРЇ
# ==================================================

def queue_embed():
    embed = discord.Embed(
        title="Freaky Tiers — Очередь тестирования",
        description=(
            "Нажмите **«Записать команду»**, чтобы встать в очередь.\n"
            "Выберите себя и своего напарника.\n\n"
            "Если передумали, нажмите **«Выйти из очереди»**.\n"
            "Выход одного участника удаляет всю пару."
        ),
        color=discord.Color.blurple()
    )

    teams = queue_data["teams"]

    if teams:
        lines = []

        for number, team in enumerate(teams, start=1):
            player_ids = team.get("players", [])

            if len(player_ids) != 2:
                continue

            player1, player2 = player_ids

            nick1 = player_names_data.get(
                str(player1), f"<@{player1}>"
            )
            nick2 = player_names_data.get(
                str(player2), f"<@{player2}>"
            )

            lines.append(
                f"**{number}.** {nick1} + {nick2} — ожидают теста"
            )

        description = "\n".join(lines) or "Очередь пуста."
        if len(description) > 1024:
            description = description[:1000] + "\n…"

        embed.add_field(
            name=f"Команд в очереди: {len(teams)}",
            value=description,
            inline=False
        )
    else:
        embed.add_field(
            name="Очередь пуста",
            value="Пока никто не записался.",
            inline=False
        )

    status = "Открыта" if queue_data["open"] else "Закрыта"
    embed.set_footer(text=f"Статус очереди: {status}")
    return embed


async def refresh_queue_message():
    channel_id = queue_data.get("channel_id")
    message_id = queue_data.get("message_id")

    if not channel_id or not message_id:
        return

    channel = bot.get_channel(channel_id)

    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            return

    try:
        message = await channel.fetch_message(message_id)
        await message.edit(
            embed=queue_embed(),
            view=QueuePostView(disabled=not queue_data["open"])
        )
    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):
        pass


# ==================================================
# РЈР”РђР›Р•РќРР• РџРђР Р« РР— РћР§Р•Р Р•Р”Р
# ==================================================

async def remove_player_team_from_queue(player_id):
    old_count = len(queue_data["teams"])

    queue_data["teams"] = [
        team for team in queue_data["teams"]
        if player_id not in team.get("players", [])
    ]

    if len(queue_data["teams"]) != old_count:
        save_queue()
        await refresh_queue_message()


# ==================================================
# Р’Р«Р”РђР§Рђ РўРР Рђ
# ==================================================

async def assign_rank(
    interaction: discord.Interaction,
    player: discord.Member,
    rank_name: str
):
    if rank_name not in TIER_ROLE_IDS:
        raise ValueError("РќРµРёР·РІРµСЃС‚РЅС‹Р№ С‚РёСЂ.")

    guild = interaction.guild
    if guild is None:
        raise ValueError("РљРѕРјР°РЅРґСѓ РЅСѓР¶РЅРѕ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ РЅР° СЃРµСЂРІРµСЂРµ.")

    target_role = guild.get_role(TIER_ROLE_IDS[rank_name])
    if target_role is None:
        raise ValueError(
            f"РќРµ РЅР°Р№РґРµРЅР° СЂРѕР»СЊ РґР»СЏ С‚РёСЂР° {rank_name}. РџСЂРѕРІРµСЂСЊ ID СЂРѕР»Рё."
        )

    roles_to_remove = []
    for tier, role_id in TIER_ROLE_IDS.items():
        role = guild.get_role(role_id)
        if role is not None and role in player.roles:
            if role.id != target_role.id:
                roles_to_remove.append(role)

    if roles_to_remove:
        await player.remove_roles(
            *roles_to_remove,
            reason=f"РР·РјРµРЅРµРЅРёРµ С‚РёСЂР° РЅР° {rank_name}"
        )

    if target_role not in player.roles:
        await player.add_roles(
            target_role,
            reason=f"РќР°Р·РЅР°С‡РµРЅ С‚РёСЂ {rank_name}"
        )

    ranks_data[str(player.id)] = rank_name
    save_json(RANKS_FILE, ranks_data)
    sync_rankings_to_website()

    # Р’С‹РґР°С‡Р° СЂР°РЅРіР° СѓРґР°Р»СЏРµС‚ РёР· РѕС‡РµСЂРµРґРё РІСЃСЋ РїР°СЂСѓ РёРіСЂРѕРєР°.
    await remove_player_team_from_queue(player.id)


# ==================================================
# РљРћРњРђРќР”Рђ /TIERS
# ==================================================

@bot.tree.command(
    name="tiers",
    description="Установить общий тир для двух игроков"
)
async def tiers(interaction: discord.Interaction):
    description = "\n".join(
        f"**{number}.** {tier}"
        for number, tier in enumerate(TIER_ORDER, start=1)
    )
    embed = discord.Embed(
        title="Freaky Tiers вЂ” РЎРїРёСЃРѕРє С‚РёСЂРѕРІ",
        description=description,
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed)


# ==================================================
# РљРћРњРђРќР”Рђ /SETRANK
# ==================================================

@bot.tree.command(name="setrank", description="Установить тир игроку")
@app_commands.describe(
    player="РРіСЂРѕРє, РєРѕС‚РѕСЂРѕРјСѓ РЅСѓР¶РЅРѕ РІС‹РґР°С‚СЊ С‚РёСЂ",
    rank_name="РљР°РєРѕР№ С‚РёСЂ РІС‹РґР°С‚СЊ"
)
@app_commands.choices(rank_name=TIER_CHOICES)
@tester_only()
async def setrank(
    interaction: discord.Interaction,
    player: discord.Member,
    rank_name: app_commands.Choice[str]
):
    await interaction.response.defer(ephemeral=True)
    try:
        await assign_rank(interaction, player, rank_name.value)
        await interaction.followup.send(
                        f"Игрок {player.mention} получил тир **{rank_name.value}**.\n"
            "Если он был в очереди, его пара удалена.",
            ephemeral=True
        )
    except (
        discord.Forbidden,
        discord.HTTPException,
        ValueError
    ) as error:
        await interaction.followup.send(
                      f"Не удалось выдать тир: {error}",
            ephemeral=True
        )


# ==================================================
# КОМАНДА /REMOVERANK
# ==================================================

@bot.tree.command(
    name="removerank",
    description="Снять тир с игрока"
)
@app_commands.describe(
    player="Игрок, у которого нужно снять тир"
)
@tester_only()
async def removerank(
    interaction: discord.Interaction,
    player: discord.Member
):
    await interaction.response.defer(ephemeral=True)

    try:
        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "Эту команду нужно использовать на сервере.",
                ephemeral=True
            )
            return

        # Удаляем все роли тиров у игрока.
        roles_to_remove = [
            role
            for role_id in TIER_ROLE_IDS.values()
            if (role := guild.get_role(role_id)) is not None
            and role in player.roles
        ]

        if roles_to_remove:
            await player.remove_roles(
                *roles_to_remove,
                reason=f"Тир снят тестером {interaction.user}"
            )

        # Удаляем тир из локального рейтинга.
        ranks_data.pop(str(player.id), None)
        save_json(RANKS_FILE, ranks_data)

        # Синхронизируем данные с сайтом.
        sync_rankings_to_website()

        # Удаляем игрока и его пару из очереди.
        await remove_player_team_from_queue(player.id)

        await interaction.followup.send(
            f"Тир игрока {player.mention} снят.",
            ephemeral=True
        )

    except (discord.Forbidden, discord.HTTPException) as error:
        await interaction.followup.send(
            f"Не удалось снять тир: {error}",
            ephemeral=True
        )

# ==================================================
# РљРћРњРђРќР”Рђ /SETTEAMRANK

# ==================================================

@bot.tree.command(
    name="setteamrank",
    description="Установить общий тир для двух игроков"
)
@app_commands.describe(
    player1="Первый игрок",
    player2="Второй игрок",
    rank_name="Тир для команды"
)
@app_commands.choices(rank_name=TIER_CHOICES)
@tester_only()
async def setteamrank(
    interaction: discord.Interaction,
    player1: discord.Member,
    player2: discord.Member,
    rank_name: app_commands.Choice[str]
):
    if player1.id == player2.id:
        await interaction.response.send_message(
            "Нужно выбрать двух разных игроков.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        id1, id2 = str(player1.id), str(player2.id)
        pair_ids = sorted((id1, id2))
        pair_key = "_".join(pair_ids)
        selected_ids = {id1, id2}

        # Удаляем старые пары, в которых состоял любой из выбранных игроков.
        for key, team in list(teams_data.items()):
            if not isinstance(team, dict):
                continue

            players = team.get("players")
            if isinstance(players, list) and any(str(pid) in selected_ids for pid in players):
                teams_data.pop(key, None)
                continue

            if key in selected_ids:
                old_teammate = team.get("teammate")
                teams_data.pop(key, None)
                if old_teammate is not None:
                    old_key = str(old_teammate)
                    old_entry = teams_data.get(old_key)
                    if isinstance(old_entry, dict) and str(old_entry.get("teammate")) == key:
                        teams_data.pop(old_key, None)

        await assign_rank(interaction, player1, rank_name.value)
        await assign_rank(interaction, player2, rank_name.value)

        # Совместимость со старым форматом данных бота.
        teams_data[id1] = {"teammate": player2.id, "rank": rank_name.value}
        teams_data[id2] = {"teammate": player1.id, "rank": rank_name.value}

        save_json(TEAMS_FILE, teams_data)
        sync_rankings_to_website()

        await interaction.followup.send(
            f"Команде {player1.mention} + {player2.mention} "
            f"назначен общий тир **{rank_name.value}**.\nПара сохранена и отправлена на сайт.",
            ephemeral=True
        )

    except (discord.Forbidden, discord.HTTPException, ValueError) as error:
        await interaction.followup.send(
            f"Не удалось назначить тир: {error}",
            ephemeral=True
        )


# ==================================================
# Р’Р«Р‘РћР  Р”Р’РЈРҐ РР“Р РћРљРћР’ Р”Р›РЇ Р—РђРџРРЎР
# ==================================================

class MinecraftNamesModal(discord.ui.Modal, title="Minecraft-ники команды"):
    my_nick = discord.ui.TextInput(
        label="Твой Minecraft-ник",
        placeholder="Введи свой ник",
        max_length=16,
        required=True
    )

    teammate_nick = discord.ui.TextInput(
        label="Minecraft-ник напарника",
        placeholder="Введи ник напарника",
        max_length=16,
        required=True
    )

    def __init__(self, player_ids, added_by):
        super().__init__()
        self.player_ids = player_ids
        self.added_by = added_by

    async def on_submit(self, interaction: discord.Interaction):
        nick1 = str(self.my_nick.value).strip()
        nick2 = str(self.teammate_nick.value).strip()

        if not nick1 or not nick2:
            await interaction.response.send_message(
                "Р—Р°РїРѕР»РЅРё РѕР±Р° Minecraft-РЅРёРєР°.",
                ephemeral=True
            )
            return

        player_names_data[str(self.player_ids[0])] = nick1
        player_names_data[str(self.player_ids[1])] = nick2
        save_json(PLAYER_NAMES_FILE, player_names_data)

        queue_data["teams"].append({
            "players": self.player_ids,
            "added_by": self.added_by,
            "player_names": [nick1, nick2]
        })

        save_queue()
        await refresh_queue_message()
        sync_rankings_to_website()

        await interaction.response.send_message(
            f"Команда добавлена: {nick1} + {nick2}",
            ephemeral=True
        )
class PairSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Выбери себя и напарника",
        min_values=2,
        max_values=2
    )
    async def select_players(
        self,
        interaction: discord.Interaction,
        select: discord.ui.UserSelect
    ):
        if not queue_data["open"]:
            await interaction.response.send_message(
                "Очередь уже закрыта.", ephemeral=True
            )
            return

        player_ids = [member.id for member in select.values]
        if len(set(player_ids)) != 2:
            await interaction.response.send_message(
                "Выберите двух разных игроков.", ephemeral=True
            )
            return

        if interaction.user.id not in player_ids:
            await interaction.response.send_message(
                "Обязательно выбери себя и своего напарника.",
                ephemeral=True
            )
            return

        for team in queue_data["teams"]:
            existing_players = team.get("players", [])
            if any(pid in existing_players for pid in player_ids):
                await interaction.response.send_message(
                    "Один из выбранных игроков уже находится в очереди.",
                    ephemeral=True
                )
                return

        teammate_id = next(
            pid for pid in player_ids
            if pid != interaction.user.id
        )

        ordered_player_ids = [
            interaction.user.id,
            teammate_id
        ]

        await interaction.response.send_modal(
            MinecraftNamesModal(
                player_ids=ordered_player_ids,
                added_by=interaction.user.id
            )
        )

# ==================================================
# РљРќРћРџРљР РћР§Р•Р Р•Р”Р
# ==================================================

class QueuePostView(discord.ui.View):
    def __init__(self, disabled=False):
        super().__init__(timeout=None)
        self.signup_button.disabled = disabled
        self.leave_button.disabled = disabled

    @discord.ui.button(
        label="Записать команду",
        style=discord.ButtonStyle.success,
        custom_id="freaky_queue_signup"
    )
    async def signup_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not queue_data["open"]:
            await interaction.response.send_message(
                "Очередь уже закрыта.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Выбери двух игроков: себя и своего напарника.",
            view=PairSelectView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="Выйти из очереди",
        style=discord.ButtonStyle.danger,
        custom_id="freaky_queue_leave"
    )
    async def leave_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        player_id = interaction.user.id
        old_count = len(queue_data["teams"])

        queue_data["teams"] = [
            team for team in queue_data["teams"]
            if player_id not in team.get("players", [])
        ]

        if len(queue_data["teams"]) == old_count:
            await interaction.response.send_message(
         "Ты не состоишь ни в одной команде очереди.",
                ephemeral=True
            )
            return

        save_queue()
        await refresh_queue_message()
        await interaction.response.send_message(
            "Ты и твой напарник удалены из очереди.",
            ephemeral=True
        )


# ==================================================
# РљРћРњРђРќР”Рђ /OPENQUEUE
# ==================================================

@bot.tree.command(name="openqueue", description="Открыть очередь")
@tester_only()
async def openqueue(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Эту команду нужно использовать на сервере.",
            ephemeral=True
        )
        return

    if queue_data["open"]:
        await interaction.response.send_message(
            "Очередь уже открыта.", ephemeral=True
        )
        return

    channel = discord.utils.get(
        interaction.guild.text_channels,
        name=QUEUE_CHANNEL_NAME
    )
    if channel is None:
        await interaction.response.send_message(
            f"Не найден канал **{QUEUE_CHANNEL_NAME}**. "
            "Проверь название канала в настройках бота.",
            ephemeral=True
        )
        return

    queue_data["open"] = True
    queue_data["teams"] = []
    queue_data["channel_id"] = channel.id
    queue_data["message_id"] = None
    save_queue()

    try:
        message = await channel.send(embed=queue_embed(), view=QueuePostView())
        queue_data["message_id"] = message.id
        save_queue()
    except (discord.Forbidden, discord.HTTPException) as error:
        queue_data["open"] = False
        save_queue()
        await interaction.response.send_message(
            f"Не удалось отправить сообщение в канал: {error}",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Очередь открыта в канале {channel.mention}.",
        ephemeral=True
    )


# ==================================================
# РљРћРњРђРќР”Рђ /CLOSEQUEUE
# ==================================================

@bot.tree.command(
    name="closequeue",
    description="Установить общий тир для двух игроков"
)
@tester_only()
async def closequeue(interaction: discord.Interaction):
    queue_data["open"] = False
    queue_data["teams"] = []
    save_queue()
    await refresh_queue_message()
    await interaction.response.send_message(
        "Очередь закрыта. Все пары удалены из очереди.",
        ephemeral=True
    )


# ==================================================
# РљРћРњРђРќР”Рђ /CLEARQUEUE
# ==================================================

@bot.tree.command(
    name="clearqueue",
    description="Установить общий тир для двух игроков"
)
@tester_only()
async def clearqueue(interaction: discord.Interaction):
    queue_data["teams"] = []
    save_queue()
    await refresh_queue_message()
    await interaction.response.send_message(
        "РћС‡РµСЂРµРґСЊ РѕС‡РёС‰РµРЅР°. Р•С‘ СЃС‚Р°С‚СѓСЃ РЅРµ РёР·РјРµРЅС‘РЅ.",
        ephemeral=True
    )


# ==================================================
# Р—РђРџРЈРЎРљ Р РЎРРќРҐР РћРќРР—РђР¦РРЇ РљРћРњРђРќР”
# ==================================================

queue_view_registered = False


@bot.event
async def on_ready():
    global queue_view_registered

    if not queue_view_registered:
        bot.add_view(QueuePostView())
        queue_view_registered = True

    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    print(f"Freaky Tiers Bot is online: {bot.user}")
    print("Slash commands synced to Freaky Tiers!")

    # РџСЂРё Р·Р°РїСѓСЃРєРµ РѕС‚РїСЂР°РІР»СЏРµРј С‚РµРєСѓС‰РёРµ СЃРѕС…СЂР°РЅС‘РЅРЅС‹Рµ РґР°РЅРЅС‹Рµ РЅР° СЃР°Р№С‚.
    sync_rankings_to_website()


if not TOKEN:
    raise RuntimeError(
        "РќРµ РЅР°Р№РґРµРЅ DISCORD_TOKEN. "
        "РЈСЃС‚Р°РЅРѕРІРё РїРµСЂРµРјРµРЅРЅСѓСЋ РѕРєСЂСѓР¶РµРЅРёСЏ СЃ С‚РѕРєРµРЅРѕРј Discord-Р±РѕС‚Р°."
    )

bot.run(TOKEN)
