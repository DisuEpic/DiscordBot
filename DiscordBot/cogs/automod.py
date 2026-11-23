import asyncio
import re
import time
from collections import OrderedDict, deque

import disnake
from disnake.ext import commands

from api import api
from config import GUILD_ONLY, log
from utils import send_log


FILTERS = {
    "invites": "Ссылки-приглашения Discord",
    "spam": "Антифлуд и повторы",
    "mentions": "Массовые упоминания",
}
SCOPES = ("all", "exclude", "only")
INVITE_PATTERN = re.compile(
    r"(?i)(^|[^a-z0-9_.-])(?:www\.)?"
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[a-z0-9-]+"
)
CHANNEL_PATTERN = re.compile(r"<#([0-9]{17,20})>|([0-9]{17,20})")
FLOOD_COUNT = 6
FLOOD_WINDOW = 10
REPEAT_COUNT = 3
REPEAT_WINDOW = 30
MENTION_LIMIT = 5
MAX_TRACKED = 8192
SAFE_MENTIONS = disnake.AllowedMentions.none()


def parse_scope(guild, mode: str | None, channels: str | None) -> dict | None:
    items = (channels or "").replace(",", " ").split()
    if mode is None:
        if items:
            raise ValueError("Укажи scope вместе с channels.")
        return None

    ids = []
    for item in items:
        match = CHANNEL_PATTERN.fullmatch(item)
        if match is None:
            raise ValueError("Указывай ID каналов или упоминания через пробел.")

        channel_id = match.group(1) or match.group(2)
        channel = guild.get_channel_or_thread(int(channel_id))
        if channel is None:
            raise ValueError("Укажи канал, ветку или категорию с этого сервера.")
        if mode == "only" and isinstance(channel, disnake.CategoryChannel):
            raise ValueError("Для only выбери канал или ветку.")
        if channel_id not in ids:
            ids.append(channel_id)

    if mode == "all" and ids:
        raise ValueError("Для all оставь channels пустым.")
    if mode == "exclude" and not 1 <= len(ids) <= 50:
        raise ValueError("Для exclude укажи от 1 до 50 каналов или категорий.")
    if mode == "only" and len(ids) != 1:
        raise ValueError("Для only укажи ровно один канал или ветку.")

    return {"mode": mode, "channelIds": ids}


def matches_scope(channel, scope: dict | None) -> bool:
    if scope is None or scope.get("mode") == "all":
        return True

    ids = {str(channel.id)}
    parent = channel.parent if isinstance(channel, disnake.Thread) else None
    if isinstance(channel, disnake.Thread) and channel.parent_id:
        ids.add(str(channel.parent_id))

    selected = {str(value) for value in scope.get("channelIds") or []}
    if scope.get("mode") == "only":
        return len(selected) == 1 and bool(ids & selected)

    category_id = getattr(parent or channel, "category_id", None)
    if category_id is not None:
        ids.add(str(category_id))

    return scope.get("mode") == "exclude" and bool(selected) and not (ids & selected)


class AutoModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.history = OrderedDict()
        self.notified = OrderedDict()
        self.checks = OrderedDict()

    @commands.slash_command(
        contexts=GUILD_ONLY, name="automod", description="Автомодерация Mirei"
    )
    @commands.default_member_permissions(manage_guild=True)
    async def automod(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @automod.sub_command(name="help", description="Фильтры, пороги и настройка каналов")
    async def help_command(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_message(
            "**Фильтры Mirei**\n"
            "`invites` — приглашения Discord.\n"
            f"`spam` — {FLOOD_COUNT}-е сообщение за {FLOOD_WINDOW} секунд "
            f"или {REPEAT_COUNT}-й подряд повтор текста за {REPEAT_WINDOW} секунд "
            "от одного человека в одном канале.\n"
            f"`mentions` — более {MENTION_LIMIT} разных упоминаний пользователей или ролей.\n\n"
            "**Настройка**\n"
            "В `/automod set` выбери фильтр, `enabled` и при необходимости `scope`.\n"
            "`all` — везде, `exclude` — кроме перечисленных, `only` — один канал и его ветки.\n"
            "Пример: `filter:invites enabled:True scope:exclude`, "
            "а в `channels` вставь ID канала партнёров.\n"
            "`/automod status` показывает текущую конфигурацию.",
            ephemeral=True,
        )

    @automod.sub_command(name="status", description="Показать настройки фильтров")
    async def status(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        config = await api.get_guild_config_for_update(str(inter.guild_id))
        if config is None:
            await inter.edit_original_response(content="API не вернуло настройки.")
            return

        settings = (config.get("security") or {}).get("automod") or {}
        scopes = settings.get("scopes") or {}
        lines = []

        for name, label in FILTERS.items():
            enabled = "включён" if settings.get(name) is True else "выключен"
            scope = scopes.get(name) or {}
            mode = scope.get("mode", "all")
            ids = scope.get("channelIds") or []
            channels = ", ".join(f"<#{channel_id}>" for channel_id in ids[:5])
            if len(ids) > 5:
                channels += f" и ещё {len(ids) - 5}"
            suffix = f" · {channels}" if channels else ""
            lines.append(f"**{label}** — {enabled} · `{mode}`{suffix}")

        await inter.edit_original_response(
            content="\n".join(lines), allowed_mentions=SAFE_MENTIONS
        )

    @automod.sub_command(name="set", description="Изменить фильтр и список каналов")
    async def set_filter(
        self,
        inter: disnake.ApplicationCommandInteraction,
        rule_filter: str = commands.Param(
            name="filter", description="Какой фильтр изменить", choices=list(FILTERS)
        ),
        enabled: bool = commands.Param(description="Включить или выключить"),
        scope: str | None = commands.Param(
            default=None, description="Где работает фильтр", choices=list(SCOPES)
        ),
        channels: str | None = commands.Param(
            default=None, description="ID каналов или упоминания через пробел"
        ),
    ):
        guild = inter.guild
        if guild is None or not inter.permissions.manage_guild:
            await inter.response.send_message(
                "Нужно право «Управлять сервером».", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        try:
            requested_scope = parse_scope(guild, scope, channels)
        except ValueError as error:
            await inter.edit_original_response(content=str(error))
            return

        config = await api.update_automod_filter(
            str(guild.id), rule_filter, enabled, requested_scope
        )
        settings = ((config or {}).get("security") or {}).get("automod") or {}
        if not isinstance(settings.get("scopes"), dict):
            await inter.edit_original_response(
                content="API не подтвердило настройки. Проверь версию C# API."
            )
            return

        current_scope = settings["scopes"].get(rule_filter) or {}
        state = "включён" if enabled else "выключен"
        await inter.edit_original_response(
            content=f"Фильтр `{rule_filter}` {state}. Область: `{current_scope.get('mode', 'all')}`."
        )

    def _spam_reason(self, message: disnake.Message) -> str | None:
        key = (message.guild.id, message.channel.id, message.author.id)
        now = time.monotonic()
        entries = self.history.pop(key, deque(maxlen=FLOOD_COUNT))
        entries.append((now, " ".join(message.content.casefold().split())))
        self.history[key] = entries
        if len(self.history) > MAX_TRACKED:
            self.history.popitem(last=False)

        if len(entries) == FLOOD_COUNT and now - entries[0][0] <= FLOOD_WINDOW:
            return f"слишком частые сообщения ({FLOOD_COUNT} за {FLOOD_WINDOW} сек.)"

        if len(entries) >= REPEAT_COUNT:
            recent = list(entries)[-REPEAT_COUNT:]
            text = recent[-1][1]
            if text and now - recent[0][0] <= REPEAT_WINDOW and all(
                content == text for _, content in recent
            ):
                return f"одинаковый текст {REPEAT_COUNT} раза подряд"

        return None

    async def _check_message(
        self, message: disnake.Message, *, edited: bool = False
    ) -> bool:
        guild = message.guild
        author = message.author
        if (
            guild is None
            or not isinstance(author, disnake.Member)
            or author.bot
            or message.webhook_id is not None
            or author.guild_permissions.manage_guild
            or message.channel.permissions_for(author).manage_messages
        ):
            return False

        config = await api.get_guild_config(str(guild.id)) or {}
        settings = (config.get("security") or {}).get("automod") or {}
        scopes = settings.get("scopes") or {}
        active = {
            name
            for name in FILTERS
            if settings.get(name) is True
            and matches_scope(message.channel, scopes.get(name))
        }

        reasons = []
        if "invites" in active and INVITE_PATTERN.search(message.content):
            reasons.append("ссылка-приглашение Discord")

        if "mentions" in active:
            mention_count = len({user.id for user in message.mentions})
            mention_count += len({role.id for role in message.role_mentions})
            if mention_count > MENTION_LIMIT:
                reasons.append(f"больше {MENTION_LIMIT} разных упоминаний")

        if "spam" in active and not edited:
            if reason := self._spam_reason(message):
                reasons.append(reason)

        if not reasons:
            return False

        reason = ", ".join(reasons)
        try:
            await message.delete()
        except disnake.NotFound:
            return True
        except disnake.HTTPException as error:
            log.warning("AutoMod: не удалось удалить сообщение %s: %s", message.id, error)
            return True

        key = (message.channel.id, author.id)
        now = time.monotonic()
        if now - self.notified.get(key, float("-inf")) < 15:
            return True

        self.notified[key] = now
        self.notified.move_to_end(key)
        if len(self.notified) > MAX_TRACKED:
            self.notified.popitem(last=False)

        try:
            await message.channel.send(
                f"{author.mention}, сообщение удалено: {reason}.",
                delete_after=8,
                allowed_mentions=SAFE_MENTIONS,
            )
        except disnake.HTTPException:
            pass

        await send_log(
            guild,
            disnake.Embed(
                title="AutoMod Mirei удалил сообщение",
                description=(
                    f"Участник: {author.mention}\n"
                    f"Канал: {message.channel.mention}\n"
                    f"Причина: {reason}"
                ),
                color=disnake.Color.orange(),
            ),
        )
        return True

    async def check_message(self, message: disnake.Message) -> bool:
        task = self.checks.get(message.id)
        if task is None:
            task = asyncio.create_task(self._check_message(message))
            self.checks[message.id] = task
            if len(self.checks) > MAX_TRACKED:
                self.checks.popitem(last=False)
        return await asyncio.shield(task)

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        await self.check_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: disnake.Message, after: disnake.Message):
        if before.content != after.content:
            await self._check_message(after, edited=True)


def setup(bot: commands.Bot):
    bot.add_cog(AutoModeration(bot))