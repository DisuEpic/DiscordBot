from __future__ import annotations

import asyncio
import re
from enum import Enum

import disnake
from disnake.ext import commands

from api import api
from config import GUILD_ONLY, log


INVITE_PATTERN = (
    r"(?i)(^|[^a-z0-9_.-])(?:www\.)?"
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/[a-z0-9-]+"
)
CHANNEL_PATTERN = re.compile(r"<#([0-9]{17,20})>|([0-9]{17,20})")
MENTION_LIMIT = 5
MAX_EXEMPT_CHANNELS = 50


class Filter(str, Enum):
    invites = "invites"
    spam = "spam"
    mentions = "mentions"

    @property
    def rule_name(self) -> str:
        return f"Mirei AutoMod: {self.value}"

    @property
    def trigger(self) -> disnake.AutoModTriggerType:
        return {
            Filter.invites: disnake.AutoModTriggerType.keyword,
            Filter.spam: disnake.AutoModTriggerType.spam,
            Filter.mentions: disnake.AutoModTriggerType.mention_spam,
        }[self]

    @property
    def warning(self) -> str:
        return {
            Filter.invites: "Приглашения Discord в этом канале запрещены.",
            Filter.spam: "Discord распознал это сообщение как спам.",
            Filter.mentions: f"В сообщении разрешено до {MENTION_LIMIT} упоминаний.",
        }[self]

    def metadata(self) -> disnake.AutoModTriggerMetadata | None:
        if self == Filter.invites:
            return disnake.AutoModTriggerMetadata(regex_patterns=[INVITE_PATTERN])
        if self == Filter.mentions:
            return disnake.AutoModTriggerMetadata(mention_total_limit=MENTION_LIMIT)
        return None


class Scope(str, Enum):
    all = "all"
    exclude = "exclude"
    only = "only"


def parse_scope(
    guild: disnake.Guild,
    scope: Scope | None,
    channels: str | None,
) -> dict | None:
    items = (channels or "").replace(",", " ").split()

    if scope is None:
        if items:
            raise ValueError("Укажи scope вместе с channels.")
        return None

    channel_ids: list[str] = []
    for item in items:
        match = CHANNEL_PATTERN.fullmatch(item)
        if match is None:
            raise ValueError("Укажи упоминания каналов или их ID через пробел.")

        channel_id = match.group(1) or match.group(2)
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            raise ValueError("Выбери канал или категорию на этом сервере.")
        if scope == Scope.only and isinstance(channel, disnake.CategoryChannel):
            raise ValueError("Для scope:only выбери канал.")

        if channel_id not in channel_ids:
            channel_ids.append(channel_id)

    if scope == Scope.all and channel_ids:
        raise ValueError("Для scope:all оставь channels пустым.")
    if scope == Scope.exclude and not 1 <= len(channel_ids) <= MAX_EXEMPT_CHANNELS:
        raise ValueError("Для scope:exclude укажи от 1 до 50 каналов или категорий.")
    if scope == Scope.only and len(channel_ids) != 1:
        raise ValueError("Для scope:only укажи ровно один канал.")

    return {"mode": scope.value, "channelIds": channel_ids}


def exempt_channel_ids(guild: disnake.Guild, scope: dict | None) -> set[int]:
    if scope is None:
        return set()

    mode = scope.get("mode")
    channel_ids = [int(channel_id) for channel_id in scope.get("channelIds", [])]

    if mode == Scope.all:
        return set()

    if mode == Scope.exclude:
        return {
            channel_id
            for channel_id in channel_ids
            if guild.get_channel(channel_id) is not None
        }

    if mode != Scope.only or len(channel_ids) != 1:
        raise ValueError("В API сохранена некорректная область фильтра.")

    target = guild.get_channel(channel_ids[0])
    if target is None or isinstance(target, disnake.CategoryChannel):
        raise ValueError("Выбранный канал недоступен. Укажи новый канал через scope:only.")

    target_category = getattr(target, "category_id", None)
    excluded: set[int] = set()

    for channel in guild.channels:
        if channel.id == target.id:
            continue

        if isinstance(channel, disnake.CategoryChannel):
            if channel.id != target_category:
                excluded.add(channel.id)
        else:
            category_id = getattr(channel, "category_id", None)
            if category_id is None or category_id == target_category:
                excluded.add(channel.id)

    if len(excluded) > MAX_EXEMPT_CHANNELS:
        raise ValueError(
            "Discord разрешает до 50 исключений. "
            "Выбери scope:exclude или сгруппируй остальные каналы в категории."
        )

    return excluded


class AutoModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._update_lock = asyncio.Lock()

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="automod",
        description="Управление автоматической модерацией Mirei",
    )
    @commands.default_member_permissions(manage_guild=True)
    async def automod(self, inter: disnake.ApplicationCommandInteraction):
        pass

    async def _get_guild(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.Guild | None:
        if inter.guild is None or not inter.permissions.manage_guild:
            await inter.response.send_message(
                "Нужно право «Управлять сервером».", ephemeral=True
            )
            return None

        if not inter.app_permissions.manage_guild:
            await inter.response.send_message(
                "Выдай Mirei право «Управлять сервером».", ephemeral=True
            )
            return None

        await inter.response.defer(ephemeral=True)
        return inter.guild

    def _find_rules(
        self, rules: list[disnake.AutoModRule], rule_filter: Filter
    ) -> list[disnake.AutoModRule]:
        return [
            rule
            for rule in rules
            if rule.creator_id == self.bot.user.id
            and rule.name == rule_filter.rule_name
            and rule.trigger_type == rule_filter.trigger
        ]

    @staticmethod
    async def _get_log_channel(guild: disnake.Guild) -> disnake.TextChannel | None:
        config = await api.get_guild_config(str(guild.id)) or {}
        channel_id = str(config.get("logChannelId") or "")
        channel = guild.get_channel(int(channel_id)) if channel_id.isdecimal() else None

        if not isinstance(channel, disnake.TextChannel):
            return None
        if channel.permissions_for(guild.default_role).view_channel:
            return None

        security = config.get("security") or {}
        verified_id = str(security.get("verificationRoleId") or "")
        if verified_id.isdecimal():
            role = guild.get_role(int(verified_id))
            if role and channel.permissions_for(role).view_channel:
                return None

        return channel

    @automod.sub_command(name="status", description="Показать фильтры и их каналы")
    async def status(self, inter: disnake.ApplicationCommandInteraction):
        guild = await self._get_guild(inter)
        if guild is None:
            return

        try:
            rules = await guild.fetch_automod_rules()
        except disnake.HTTPException as error:
            log.warning("AutoMod: не удалось получить правила для %s: %s", guild.id, error)
            await inter.edit_original_response(content="Discord не вернул список правил.")
            return

        config = await api.get_guild_config(str(guild.id)) or {}
        saved = (config.get("security") or {}).get("automod") or {}
        scopes = saved.get("scopes")
        lines = []

        for rule_filter in Filter:
            matching = self._find_rules(rules, rule_filter)
            actual = any(rule.enabled for rule in matching)

            if len(matching) > 1:
                lines.append(f"**{rule_filter.value}** — в Discord есть дубликаты.")
                continue

            discord_state = "включён" if actual else "выключен"
            line = f"**{rule_filter.value}** — Discord: {discord_state}"

            if not isinstance(scopes, dict):
                lines.append(f"{line} · настройки API недоступны")
                continue

            desired = saved.get(rule_filter.value)
            if desired is None:
                lines.append(f"{line} · в API ещё не настроен")
                continue

            scope = scopes.get(rule_filter.value)
            mode = scope["mode"] if scope else "all"
            api_state = "включён" if desired else "выключен"
            line += f" · API: {api_state}, `{mode}`"

            if scope and scope.get("channelIds"):
                channel_mentions = ", ".join(
                    f"<#{channel_id}>" for channel_id in scope["channelIds"][:5]
                )
                remaining = len(scope["channelIds"]) - 5
                if remaining > 0:
                    channel_mentions += f" и ещё {remaining}"
                line += f" ({channel_mentions})"

            if desired != actual:
                line += " · повтори `/automod set` для синхронизации"
            elif actual:
                try:
                    expected = exempt_channel_ids(guild, scope)
                    if expected != set(matching[0].exempt_channel_ids):
                        line += " · исключения расходятся, повтори `/automod set`"
                except ValueError as error:
                    line += f" · {error}"

            lines.append(line)

        await inter.edit_original_response(
            content="\n".join(lines),
            allowed_mentions=disnake.AllowedMentions.none(),
        )

    @automod.sub_command(name="set", description="Настроить фильтр и область действия")
    async def set_filter(
        self,
        inter: disnake.ApplicationCommandInteraction,
        rule_filter: Filter = commands.Param(name="filter", description="Фильтр AutoMod"),
        enabled: bool = commands.Param(description="Включить фильтр"),
        scope: Scope | None = commands.Param(
            default=None, description="Область действия фильтра"
        ),
        channels: str | None = commands.Param(
            default=None, description="Упоминания или ID каналов через пробел"
        ),
    ):
        guild = await self._get_guild(inter)
        if guild is None:
            return

        reason = f"Mirei AutoMod: настройка от {inter.author.id}"
        saved = False

        try:
            requested_scope = parse_scope(guild, scope, channels)
            if enabled and requested_scope is not None:
                exempt_channel_ids(guild, requested_scope)

            async with self._update_lock:
                config = await api.update_automod_filter(
                    str(guild.id), rule_filter.value, enabled, requested_scope
                )
                if config is None:
                    result = "API не подтвердило сохранение. Повтори команду."
                else:
                    saved = True
                    automod = (config.get("security") or {}).get("automod") or {}
                    scopes = automod.get("scopes")

                    if not isinstance(scopes, dict):
                        result = "API не вернуло настройки каналов. Проверь версию API."
                    else:
                        result = await self._apply_rule(
                            guild, rule_filter, enabled, scopes.get(rule_filter.value), reason
                        )
        except ValueError as error:
            prefix = "Настройка сохранена в API, но не применена. " if saved else ""
            result = f"{prefix}{error}"
        except disnake.Forbidden:
            result = (
                "Настройка сохранена в API. Discord отказал в изменении правила. "
                "Проверь право Mirei «Управлять сервером» и повтори команду."
            )
        except disnake.HTTPException as error:
            log.warning("AutoMod %s/%s: %s", guild.id, rule_filter.value, error)
            result = (
                "Настройка сохранена в API. Discord отклонил изменение. "
                "Проверь правила AutoMod сервера и повтори команду."
            )

        await inter.edit_original_response(
            content=result,
            allowed_mentions=disnake.AllowedMentions.none(),
        )

    async def _apply_rule(
        self,
        guild: disnake.Guild,
        rule_filter: Filter,
        enabled: bool,
        scope: dict | None,
        reason: str,
    ) -> str:
        rules = await guild.fetch_automod_rules()
        matching = self._find_rules(rules, rule_filter)

        if len(matching) > 1:
            return "Настройка сохранена в API. Удали дубликаты правила Mirei в Discord."

        rule = matching[0] if matching else None
        if not enabled:
            if rule is not None and rule.enabled:
                await rule.edit(enabled=False, reason=reason)
            return "Фильтр выключен."

        ids = exempt_channel_ids(guild, scope)
        exempt_channels = [disnake.Object(id=channel_id) for channel_id in sorted(ids)]
        mode = scope["mode"] if scope else "all"

        if rule is not None:
            if not rule.enabled or set(rule.exempt_channel_ids) != ids:
                await rule.edit(
                    enabled=True,
                    exempt_channels=exempt_channels,
                    reason=reason,
                )
            return f"Фильтр включён. Область: `{mode}`."

        if rule_filter in (Filter.spam, Filter.mentions) and any(
            existing.trigger_type == rule_filter.trigger for existing in rules
        ):
            return (
                "Настройка сохранена в API. Discord уже содержит правило этого типа. "
                "Его область можно настроить в настройках сервера."
            )

        actions: list[disnake.AutoModAction] = [
            disnake.AutoModBlockMessageAction(rule_filter.warning)
        ]
        log_channel = await self._get_log_channel(guild)
        if log_channel is not None:
            actions.append(disnake.AutoModSendAlertAction(log_channel))

        await guild.create_automod_rule(
            name=rule_filter.rule_name,
            event_type=disnake.AutoModEventType.message_send,
            trigger_type=rule_filter.trigger,
            trigger_metadata=rule_filter.metadata(),
            actions=actions,
            enabled=True,
            exempt_channels=exempt_channels,
            reason=reason,
        )
        return f"Фильтр включён. Область: `{mode}`."


def setup(bot: commands.Bot):
    bot.add_cog(AutoModeration(bot))