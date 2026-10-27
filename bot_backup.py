
import os
import json
import requests
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

# ==================================================
# НАСТРОЙКИ
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
# СОЗДАНИЕ БОТА
# ==================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==================================================
# JSON: СОХРАНЕНИЕ И ЗАГРУЗКА
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

# ==================================================
# СИНХРОНИЗАЦИЯ С САЙТОМ
# ==================================================

def sync_rankings_to_website():
    """Отправляет текущие тиры и команды на сайт."""
    if not WEBSITE_SYNC_URL or not WEBSITE_SYNC_SECRET:
        print("[Website sync] Не заданы WEBSITE_SYNC_URL или WEBSITE_SYNC_SECRET.")
        return

    try:
        response = requests.post(
            f"{WEBSITE_SYNC_URL}/api/sync",
            json={
                "ranks": ranks_data,
                "teams": teams_data,
            },
            headers={
                "Authorization": f"Bearer {WEBSITE_SYNC_SECRET}",
            },
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
# ПРОВЕРКА ПРАВ ТЕСТЕРА
# ==================================================

def is_tester(member):
    if not isinstance(member, discord.Member):
        return False

    return any(role.id == TESTER_ROLE_ID for role in member.roles)


def tester_only():
    async def predicate(interaction: discord.Interaction):
        if not is_tester(interaction.user):
            raise app_commands.CheckFailure(
                "Эта команда доступна только тестерам."
            )
        return True

    return app_commands.check(predicate)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CheckFailure):
        message = str(error) or "У тебя нет прав на эту команду."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return

    print(f"Ошибка команды: {error}")
    message = "Произошла ошибка при выполнении команды."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ==================================================
# ОЧЕРЕДЬ: ОБНОВЛЕНИЕ СООБЩЕНИЯ
# ==================================================

def queue_embed():
    embed = discord.Embed(
        title="Freaky Tiers — Test Queue",
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
            lines.append(
                f"**{number}.** <@{player1}> + <@{player2}> "
                "— ожидают теста"
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
# УДАЛЕНИЕ ПАРЫ ИЗ ОЧЕРЕДИ
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
# ВЫДАЧА ТИРА
# ==================================================

async def assign_rank(
    interaction: discord.Interaction,
    player: discord.Member,
    rank_name: str
):
    if rank_name not in TIER_ROLE_IDS:
        raise ValueError("Неизвестный тир.")

    guild = interaction.guild
    if guild is None:
        raise ValueError("Команду нужно использовать на сервере.")

    target_role = guild.get_role(TIER_ROLE_IDS[rank_name])
    if target_role is None:
        raise ValueError(
            f"Не найдена роль для тира {rank_name}. Проверь ID роли."
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
            reason=f"Изменение тира на {rank_name}"
        )

    if target_role not in player.roles:
        await player.add_roles(
            target_role,
            reason=f"Назначен тир {rank_name}"
        )

    ranks_data[str(player.id)] = rank_name
    save_json(RANKS_FILE, ranks_data)
    sync_rankings_to_website()

    # Выдача ранга удаляет из очереди всю пару игрока.
    await remove_player_team_from_queue(player.id)


# ==================================================
# КОМАНДА /TIERS
# ==================================================

@bot.tree.command(
    name="tiers",
    description="Показать список всех тиров Freaky Tiers"
)
async def tiers(interaction: discord.Interaction):
    description = "\n".join(
        f"**{number}.** {tier}"
        for number, tier in enumerate(TIER_ORDER, start=1)
    )
    embed = discord.Embed(
        title="Freaky Tiers — Список тиров",
        description=description,
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed)


# ==================================================
# КОМАНДА /SETRANK
# ==================================================

@bot.tree.command(name="setrank", description="Выдать игроку тир")
@app_commands.describe(
    player="Игрок, которому нужно выдать тир",
    rank_name="Какой тир выдать"
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
# КОМАНДА /SETTEAMRANK
# ==================================================

@bot.tree.command(
    name="setteamrank",
    description="Выдать общий тир двум игрокам и сохранить их как команду"
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
        await assign_rank(interaction, player1, rank_name.value)
        await assign_rank(interaction, player2, rank_name.value)

        # Удаляем старые связи этих игроков с напарниками.
        for player_id in (str(player1.id), str(player2.id)):
            old_team = teams_data.get(player_id)

            if isinstance(old_team, dict):
                old_teammate = old_team.get("teammate")

                if old_teammate is not None:
                    old_teammate_id = str(old_teammate)
                    old_teammate_data = teams_data.get(old_teammate_id)

                    if (
                        isinstance(old_teammate_data, dict)
                        and str(old_teammate_data.get("teammate")) == player_id
                    ):
                        teams_data.pop(old_teammate_id, None)

            teams_data.pop(player_id, None)

        # Сохраняем новую команду в обе стороны.
        teams_data[str(player1.id)] = {
            "teammate": player2.id,
            "rank": rank_name.value
        }
        teams_data[str(player2.id)] = {
            "teammate": player1.id,
            "rank": rank_name.value
        }

        save_json(TEAMS_FILE, teams_data)
        sync_rankings_to_website()

        await interaction.followup.send(
            f"Команде {player1.mention} и {player2.mention} "
            f"выдан общий тир **{rank_name.value}**.\n"
            "Если игроки были в очереди, их пары удалены.",
            ephemeral=True
        )
    except (
        discord.Forbidden,
        discord.HTTPException,
        ValueError
    ) as error:
        await interaction.followup.send(
            f"Не удалось назначить тир: {error}",
            ephemeral=True
        )


# ==================================================
# КОМАНДА /RANK
# ==================================================

@bot.tree.command(
    name="rank",
    description="Посмотреть тир игрока и его напарника"
)
@app_commands.describe(player="Игрок, чей тир нужно посмотреть")
async def rank(interaction: discord.Interaction, player: discord.Member):
    player_rank = ranks_data.get(str(player.id), "Не установлен")
    team_info = teams_data.get(str(player.id))
    teammate_text = "Не указан"

    if isinstance(team_info, dict):
        teammate_id = team_info.get("teammate")
        if teammate_id:
            teammate_text = f"<@{teammate_id}>"

    embed = discord.Embed(
        title=f"Тир игрока {player.display_name}",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Игрок", value=player.mention, inline=False)
    embed.add_field(name="Тир", value=f"**{player_rank}**", inline=True)
    embed.add_field(name="Напарник", value=teammate_text, inline=True)
    await interaction.response.send_message(embed=embed)


# ==================================================
# ВЫБОР ДВУХ ИГРОКОВ ДЛЯ ЗАПИСИ
# ==================================================

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

        queue_data["teams"].append({
            "players": player_ids,
            "added_by": interaction.user.id
        })
        save_queue()
        await refresh_queue_message()

        await interaction.response.send_message(
            "Ваша команда добавлена в очередь!", ephemeral=True
        )


# ==================================================
# КНОПКИ ОЧЕРЕДИ
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
                "Очередь закрыта.", ephemeral=True
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
# КОМАНДА /OPENQUEUE
# ==================================================

@bot.tree.command(name="openqueue", description="Открыть очередь на тесты")
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
# КОМАНДА /CLOSEQUEUE
# ==================================================

@bot.tree.command(
    name="closequeue",
    description="Закрыть очередь и удалить все команды"
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
# КОМАНДА /CLEARQUEUE
# ==================================================

@bot.tree.command(
    name="clearqueue",
    description="Удалить все пары из очереди, не закрывая её"
)
@tester_only()
async def clearqueue(interaction: discord.Interaction):
    queue_data["teams"] = []
    save_queue()
    await refresh_queue_message()
    await interaction.response.send_message(
        "Очередь очищена. Её статус не изменён.",
        ephemeral=True
    )


# ==================================================
# ЗАПУСК И СИНХРОНИЗАЦИЯ КОМАНД
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

    # При запуске отправляем текущие сохранённые данные на сайт.
    sync_rankings_to_website()


if not TOKEN:
    raise RuntimeError(
        "Не найден DISCORD_TOKEN. "
        "Установи переменную окружения с токеном Discord-бота."
    )

bot.run(TOKEN)
