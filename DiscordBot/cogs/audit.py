import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import disnake
from disnake.ext import commands

from api import api
from config import (
    ACCENT_GOLD, COMBAT_RED, TACTICAL_GREEN, BRAND_COLOR, UNIFIED_FOOTER,
    RAID_WINDOW_SECONDS, RAID_JOIN_THRESHOLD, RAID_ALERT_COOLDOWN, YOUNG_ACCOUNT_DAYS,
)
from utils import send_log, send_welcome_card


AUDIT_DELETE_FETCH_COOLDOWN = 2.5
_audit_fetch_timestamps: Dict[Tuple[int, str], float] = {}


def is_safe_to_restore_role(
    role: disnake.Role, bot_top_role: disnake.Role | None
) -> bool:
    if role.is_default() or role.managed:
        return False
    if bot_top_role is not None and role >= bot_top_role:
        return False

    perms = role.permissions
    return not any((
        perms.administrator,
        perms.manage_guild,
        perms.manage_roles,
        perms.manage_channels,
        perms.ban_members,
        perms.kick_members,
        perms.moderate_members,
        perms.manage_messages,
        perms.manage_webhooks,
        perms.manage_threads,
        perms.mention_everyone,
    ))


async def fetch_recent_audit_entry(
    guild: disnake.Guild,
    action: disnake.AuditLogAction,
    target_id: Optional[int] = None,
    max_age_seconds: float = 8.0,
    min_interval_seconds: float = 0.0,
) -> Optional[disnake.AuditLogEntry]:
    if not guild.me or not guild.me.guild_permissions.view_audit_log:
        return None

    now_mono = time.monotonic()
    if min_interval_seconds > 0:
        key = (guild.id, str(action))
        last_fetch = _audit_fetch_timestamps.get(key, 0.0)
        if now_mono - last_fetch < min_interval_seconds:
            return None
        if len(_audit_fetch_timestamps) > 1000:
            _audit_fetch_timestamps.clear()
        _audit_fetch_timestamps[key] = now_mono

    try:
        now = disnake.utils.utcnow()
        async for entry in guild.audit_logs(limit=5, action=action):
            if (now - entry.created_at).total_seconds() > max_age_seconds:
                continue
            if target_id is None or (entry.target and entry.target.id == target_id):
                return entry
    except disnake.HTTPException:
        pass
    return None


class Audit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent_joins: Dict[int, deque] = {}
        self._last_raid_alert: Dict[int, float] = {}
        self._restoring_members: Dict[Tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot or not message.guild:
            return

        cfg = await api.get_guild_config(str(message.guild.id))
        trap_channel_id = ((cfg or {}).get("security") or {}).get("trapChannelId")
        if not trap_channel_id or str(message.channel.id) != str(trap_channel_id):
            return

        member = message.author
        if (
            member.guild_permissions.manage_messages
            or member.guild_permissions.administrator
            or member.id == message.guild.owner_id
        ):
            return

        try:
            await message.delete()
        except disnake.Forbidden:
            pass

        try:
            dm_embed = disnake.Embed(
                title="⛔ Вы были исключены с сервера",
                description=(
                    f"Вы нарушили правило канала **#{message.channel.name}** "
                    f"на сервере **{message.guild.name}**, в котором запрещено писать."
                ),
                color=COMBAT_RED,
            )
            dm_embed.set_footer(text=UNIFIED_FOOTER)
            await member.send(embed=dm_embed)
        except disnake.Forbidden:
            pass

        try:
            await member.kick(reason=f"Сообщение в канале тишины #{message.channel.name}")
            log_embed = disnake.Embed(
                title="🚨 Исключение (Канал тишины)",
                description=(
                    f"**Участник:** {member.mention} (`{member.id}`)\n"
                    f"**Канал:** {message.channel.mention}"
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(message.guild, log_embed)
        except disnake.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: disnake.Message):
        if message.author.bot or not message.guild:
            return

        deleter_text = ""
        entry = await fetch_recent_audit_entry(
            message.guild,
            disnake.AuditLogAction.message_delete,
            target_id=message.author.id,
            min_interval_seconds=AUDIT_DELETE_FETCH_COOLDOWN,
        )
        if entry and entry.user and entry.user.id != message.author.id:
            deleter_text = f"\n**Удалил модератор:** {entry.user.mention}"

        embed = disnake.Embed(
            title="🗑️ Сообщение удалено",
            description=(
                f"**Автор:** {message.author.mention} (`{message.author.id}`)\n"
                f"**Канал:** {message.channel.mention}"
                f"{deleter_text}"
            ),
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        content_text = (
            message.content[:1024]
            if message.content
            else "*Сообщение было пустым или содержало только файлы*"
        )
        embed.add_field(name="Содержимое:", value=content_text, inline=False)
        if message.attachments:
            embed.add_field(name="Вложения:", value=f"{len(message.attachments)} шт.", inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: List[disnake.Message]):
        if not messages or not messages[0].guild:
            return

        guild = messages[0].guild
        channel = messages[0].channel
        embed = disnake.Embed(
            title="🧹 Массовая очистка сообщений",
            description=f"**Канал:** {channel.mention}\n**Удалено сообщений:** `{len(messages)}` шт.",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: disnake.Message, after: disnake.Message):
        if after.author.bot or not after.guild or before.content == after.content:
            return

        old_content = before.content or "*[Не сохранено в кэше]*"
        new_content = after.content or "*[Пустое сообщение]*"
        embed = disnake.Embed(
            title="✏️ Сообщение отредактировано",
            description=(
                f"**Автор:** {after.author.mention} (`{after.author.id}`)\n"
                f"**Канал:** {after.channel.mention} "
                f"([Перейти к сообщению]({after.jump_url}))"
            ),
            color=ACCENT_GOLD,
            timestamp=disnake.utils.utcnow(),
        )
        embed.add_field(name="До:", value=old_content[:1000], inline=False)
        embed.add_field(name="После:", value=new_content[:1000], inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: disnake.RawMessageDeleteEvent):
        if payload.cached_message is not None or payload.guild_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        embed = disnake.Embed(
            title="🗑️ Сообщение удалено",
            description=(
                f"**Канал:** <#{payload.channel_id}>\n"
                f"**ID сообщения:** `{payload.message_id}`\n"
                "*Текст сообщения отсутствует в кэше.*"
            ),
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: disnake.RawMessageUpdateEvent):
        if payload.cached_message is not None or payload.guild_id is None:
            return

        data = payload.data or {}
        if not data.get("edited_timestamp") or "content" not in data:
            return

        author = data.get("author") or {}
        if author.get("bot"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        embed = disnake.Embed(
            title="✏️ Сообщение отредактировано",
            description=(
                f"**Автор:** <@{author.get('id', 0)}>\n"
                f"**Канал:** <#{payload.channel_id}>\n"
                f"**ID сообщения:** `{payload.message_id}`"
            ),
            color=ACCENT_GOLD,
            timestamp=disnake.utils.utcnow(),
        )
        embed.add_field(
            name="Новый текст:", value=(data.get("content") or "*Пусто*")[:1000], inline=False
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member):
        now = time.time()
        for guild_id in list(self._recent_joins):
            queue = self._recent_joins[guild_id]
            while queue and now - queue[0] > RAID_WINDOW_SECONDS:
                queue.popleft()
            if not queue and guild_id != member.guild.id:
                del self._recent_joins[guild_id]

        joins = self._recent_joins.setdefault(member.guild.id, deque())
        joins.append(now)

        age_days = (disnake.utils.utcnow() - member.created_at).days
        young = age_days < YOUNG_ACCOUNT_DAYS
        restored_roles: List[disnake.Role] = []

        cfg = await api.get_guild_config(str(member.guild.id)) or {}
        security = cfg.get("security") or {}
        verify_role_id = security.get("verificationRoleId")

        if not member.bot:
            profile = await api.get_user_profile(str(member.guild.id), str(member.id))
            if profile:
                saved_role_ids = {str(role_id) for role_id in profile.get("roles") or []}
                if verify_role_id:
                    saved_role_ids.discard(str(verify_role_id))
                    if profile.get("isVerified"):
                        saved_role_ids.add(str(verify_role_id))

                bot_top_role = member.guild.me.top_role if member.guild.me else None
                roles_to_add = []
                for role_id in saved_role_ids:
                    if not role_id.isdigit():
                        continue
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles and is_safe_to_restore_role(role, bot_top_role):
                        roles_to_add.append(role)

                if roles_to_add:
                    key = (member.guild.id, member.id)
                    try:
                        self._restoring_members[key] = time.time()
                        await member.add_roles(*roles_to_add, reason="Автовосстановление ролей из базы")
                        restored_roles = roles_to_add
                    except disnake.HTTPException:
                        self._restoring_members.pop(key, None)

            verify_role = (
                member.guild.get_role(int(verify_role_id))
                if verify_role_id and str(verify_role_id).isdigit()
                else None
            )
            if not verify_role or (profile and profile.get("isVerified")):
                await send_welcome_card(member, cfg, extra_roles=restored_roles)

        embed = disnake.Embed(
            title="📥 Новый участник на сервере",
            description=f"**Участник:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`",
            color=COMBAT_RED if young else TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Возраст аккаунта",
            value=f"{age_days} дн." + (" ⚠️ **новый аккаунт**" if young else ""),
            inline=True,
        )
        if restored_roles:
            embed.add_field(
                name="♻️ Восстановлены роли из БД",
                value=", ".join(role.mention for role in restored_roles)[:1024],
                inline=False,
            )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(member.guild, embed)

        current_time = time.time()
        for key, timestamp in list(self._restoring_members.items()):
            if current_time - timestamp > 10:
                self._restoring_members.pop(key, None)

        if (
            len(joins) >= RAID_JOIN_THRESHOLD
            and now - self._last_raid_alert.get(member.guild.id, 0) > RAID_ALERT_COOLDOWN
        ):
            if len(self._last_raid_alert) > 500:
                self._last_raid_alert = {
                    guild_id: timestamp
                    for guild_id, timestamp in self._last_raid_alert.items()
                    if now - timestamp <= RAID_ALERT_COOLDOWN
                }

            self._last_raid_alert[member.guild.id] = now
            alert = disnake.Embed(
                title="🚨 ВОЗМОЖНЫЙ РЕЙД",
                description=(
                    f"За последние **{RAID_WINDOW_SECONDS} сек.** "
                    f"на сервер зашло **{len(joins)}** участников.\n"
                    "При необходимости ограничьте отправку сообщений командой `/модерация закрыть`."
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
            alert.set_footer(text=UNIFIED_FOOTER)
            await send_log(member.guild, alert)

    @commands.Cog.listener()
    async def on_member_remove(self, member: disnake.Member):
        entry = await fetch_recent_audit_entry(
            member.guild, disnake.AuditLogAction.kick, target_id=member.id
        )
        if entry and entry.user and entry.user.id != self.bot.user.id:
            reason = entry.reason or "Причина не указана"
            embed = disnake.Embed(
                title="👢 Участник исключён",
                description=(
                    f"**Исключён:** {member.mention} (`{member.id}`)\n"
                    f"**Модератор:** {entry.user.mention}\n"
                    f"**Причина:** {reason}"
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
        else:
            embed = disnake.Embed(
                title="🚪 Участник покинул сервер",
                description=f"**Участник:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`",
                color=disnake.Color.dark_grey(),
                timestamp=disnake.utils.utcnow(),
            )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: disnake.Guild, user: disnake.User):
        entry = await fetch_recent_audit_entry(guild, disnake.AuditLogAction.ban, target_id=user.id)
        if entry and entry.user and entry.user.id == self.bot.user.id:
            return

        moderator = f"\n**Модератор:** {entry.user.mention}" if entry and entry.user else ""
        reason = f"\n**Причина:** {entry.reason}" if entry and entry.reason else ""
        embed = disnake.Embed(
            title="🔨 Участник заблокирован",
            description=f"**Заблокирован:** {user.mention} (`{user.id}`){moderator}{reason}",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: disnake.Guild, user: disnake.User):
        entry = await fetch_recent_audit_entry(guild, disnake.AuditLogAction.unban, target_id=user.id)
        if entry and entry.user and entry.user.id == self.bot.user.id:
            return

        moderator = f"\n**Модератор:** {entry.user.mention}" if entry and entry.user else ""
        reason = f"\n**Причина:** {entry.reason}" if entry and entry.reason else ""
        embed = disnake.Embed(
            title="🔓 Пользователь разблокирован",
            description=f"**Пользователь:** {user.mention} (`{user.id}`){moderator}{reason}",
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: disnake.Member, after: disnake.Member):
        if after.bot:
            return

        if before.nick != after.nick:
            embed = disnake.Embed(
                title="📝 Изменение никнейма",
                description=f"**Участник:** {after.mention} (`{after.id}`)",
                color=ACCENT_GOLD,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Было:", value=f"`{before.nick or before.name}`", inline=True)
            embed.add_field(name="Стало:", value=f"`{after.nick or after.name}`", inline=True)
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(after.guild, embed)

        if before.current_timeout != after.current_timeout:
            entry = await fetch_recent_audit_entry(
                after.guild, disnake.AuditLogAction.member_update, target_id=after.id
            )
            if not (entry and entry.user and entry.user.id == self.bot.user.id):
                moderator = entry.user.mention if entry and entry.user else "Неизвестно"
                if after.current_timeout and after.current_timeout > disnake.utils.utcnow():
                    until = disnake.utils.format_dt(after.current_timeout, style="f")
                    embed = disnake.Embed(
                        title="🔇 Применён таймаут",
                        description=(
                            f"**Участник:** {after.mention} (`{after.id}`)\n"
                            f"**Модератор:** {moderator}\n**До:** {until}"
                        ),
                        color=ACCENT_GOLD,
                        timestamp=disnake.utils.utcnow(),
                    )
                    embed.set_footer(text=UNIFIED_FOOTER)
                    await send_log(after.guild, embed)
                elif before.current_timeout and after.current_timeout is None:
                    embed = disnake.Embed(
                        title="🔊 Таймаут снят",
                        description=(
                            f"**Участник:** {after.mention} (`{after.id}`)\n"
                            f"**Модератор:** {moderator}"
                        ),
                        color=TACTICAL_GREEN,
                        timestamp=disnake.utils.utcnow(),
                    )
                    embed.set_footer(text=UNIFIED_FOOTER)
                    await send_log(after.guild, embed)

        if before.roles == after.roles:
            return

        added_roles = [role for role in after.roles if role not in before.roles and not role.is_default()]
        removed_roles = [role for role in before.roles if role not in after.roles and not role.is_default()]
        if not added_roles and not removed_roles:
            return

        restore_time = self._restoring_members.get((after.guild.id, after.id))
        if restore_time and time.time() - restore_time < 4.0:
            return

        await api.update_user_roles_batch(
            str(after.guild.id),
            str(after.id),
            [str(role.id) for role in added_roles],
            [str(role.id) for role in removed_roles],
        )

        embed = disnake.Embed(
            title="🎭 Изменение ролей участника",
            description=f"**Участник:** {after.mention} (`{after.id}`)",
            color=BRAND_COLOR,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        if added_roles:
            embed.add_field(
                name="🟢 Выданы:",
                value=", ".join(role.mention for role in added_roles)[:1024],
                inline=False,
            )
        if removed_roles:
            embed.add_field(
                name="🔴 Сняты:",
                value=", ".join(role.mention for role in removed_roles)[:1024],
                inline=False,
            )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState
    ):
        if member.bot or before.channel == after.channel:
            return

        cfg = await api.get_guild_config(str(member.guild.id))
        generator_id = ((cfg or {}).get("voice") or {}).get("generatorChannelId")
        generator_id = str(generator_id) if generator_id else None
        if after.channel and str(after.channel.id) == generator_id:
            return

        member_text = f"**Участник:** {member.mention} (`{member.id}`)"
        if before.channel is None and after.channel is not None:
            title = "🔊 Подключение к голосовому каналу"
            description = f"{member_text}\n**Канал:** {after.channel.mention}"
            color = TACTICAL_GREEN
        elif before.channel is not None and after.channel is None:
            title = "🔇 Отключение от голосового канала"
            description = f"{member_text}\n**Канал:** {before.channel.mention}"
            color = disnake.Color.dark_grey()
        elif before.channel is not None and after.channel is not None:
            if str(before.channel.id) == generator_id:
                title = "🔊 Создана приватная комната"
                description = (
                    f"**Владелец:** {member.mention} (`{member.id}`)\n"
                    f"**Канал:** {after.channel.mention}"
                )
                color = TACTICAL_GREEN
            else:
                title = "🔀 Смена голосового канала"
                description = f"{member_text}\n**Из:** {before.channel.mention} ➔ **В:** {after.channel.mention}"
                color = ACCENT_GOLD
        else:
            return

        embed = disnake.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(member.guild, embed)

    async def _is_stats_channel(self, guild_id: int, channel_id: int) -> bool:
        stats_cog = self.bot.get_cog("Stats")
        if stats_cog and channel_id in getattr(stats_cog, "ignored_audit_ids", set()):
            return True

        cfg = await api.get_guild_config(str(guild_id)) or {}
        stats = cfg.get("stats") or {}
        fields = (
            "categoryId", "allMembersChannelId", "membersChannelId", "botsChannelId",
            "channelsChannelId", "rolesChannelId", "voiceChannelId",
        )
        return any(str(stats.get(field)) == str(channel_id) for field in fields)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: disnake.abc.GuildChannel):
        if await self._is_stats_channel(channel.guild.id, channel.id):
            return

        voice_cog = self.bot.get_cog("VoiceHub")
        if voice_cog and channel.id in getattr(voice_cog, "temp_channels", {}):
            return

        entry = await fetch_recent_audit_entry(
            channel.guild, disnake.AuditLogAction.channel_create, target_id=channel.id
        )
        creator = f"\n**Создал:** {entry.user.mention}" if entry and entry.user else ""

        if isinstance(channel, disnake.TextChannel):
            channel_type = "💬 Текстовый"
        elif isinstance(channel, disnake.VoiceChannel):
            channel_type = "🔊 Голосовой"
        else:
            channel_type = "📁 Категория"

        embed = disnake.Embed(
            title="📁 Создан новый канал",
            description=(
                f"**Канал:** {channel.mention} (`#{channel.name}`)\n"
                f"**Тип:** {channel_type}{creator}"
            ),
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow(),
        )
        if channel.category:
            embed.add_field(name="Категория:", value=f"`{channel.category.name}`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: disnake.abc.GuildChannel):
        if await self._is_stats_channel(channel.guild.id, channel.id):
            return

        voice_cog = self.bot.get_cog("VoiceHub")
        deleted_temp_ids = getattr(voice_cog, "deleted_temp_ids", set())
        if channel.id in deleted_temp_ids:
            deleted_temp_ids.discard(channel.id)
            return

        entry = await fetch_recent_audit_entry(
            channel.guild, disnake.AuditLogAction.channel_delete, target_id=channel.id
        )
        deleter = f"\n**Удалил:** {entry.user.mention}" if entry and entry.user else ""

        if isinstance(channel, disnake.TextChannel):
            channel_type = "💬 Текстовый"
        elif isinstance(channel, disnake.VoiceChannel):
            channel_type = "🔊 Голосовой"
        else:
            channel_type = "📁 Категория"

        embed = disnake.Embed(
            title="🗑️ Канал удалён",
            description=f"**Название:** `#{channel.name}`\n**Тип:** {channel_type}{deleter}",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: disnake.abc.GuildChannel, after: disnake.abc.GuildChannel
    ):
        if await self._is_stats_channel(after.guild.id, after.id):
            return

        changes = []
        if before.name != after.name:
            changes.append(f"• **Переименование:** `#{before.name}` ➔ `#{after.name}`")
        if isinstance(before, disnake.TextChannel) and isinstance(after, disnake.TextChannel):
            if before.topic != after.topic:
                old_topic = before.topic or "*Отсутствует*"
                new_topic = after.topic or "*Отсутствует*"
                changes.append(f"• **Тема канала:** `{old_topic}` ➔ `{new_topic}`")

        if not changes:
            return

        embed = disnake.Embed(
            title="⚙️ Параметры канала изменены",
            description=f"**Канал:** {after.mention}\n\n" + "\n".join(changes),
            color=ACCENT_GOLD,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: disnake.Role):
        entry = await fetch_recent_audit_entry(
            role.guild, disnake.AuditLogAction.role_create, target_id=role.id
        )
        creator = f"\n**Создал:** {entry.user.mention}" if entry and entry.user else ""

        embed = disnake.Embed(
            title="✨ Создана новая роль",
            description=f"**Роль:** {role.mention} (`{role.name}`)\n**Цвет:** `{role.color}`{creator}",
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: disnake.Role):
        entry = await fetch_recent_audit_entry(
            role.guild, disnake.AuditLogAction.role_delete, target_id=role.id
        )
        deleter = f"\n**Удалил:** {entry.user.mention}" if entry and entry.user else ""

        embed = disnake.Embed(
            title="🔥 Роль сервера удалена",
            description=f"**Бывшее название:** `{role.name}`\n**ID роли:** `{role.id}`{deleter}",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(role.guild, embed)


def setup(bot: commands.Bot):
    bot.add_cog(Audit(bot))