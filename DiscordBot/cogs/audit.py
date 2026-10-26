import time
import disnake
from disnake.ext import commands
from typing import List, Dict
from collections import deque
from api import api
from utils import send_log
from config import (
    AIGIS_GOLD, COMBAT_RED, TACTICAL_GREEN, P3_BLUE, UNIFIED_FOOTER,
    RAID_WINDOW_SECONDS, RAID_JOIN_THRESHOLD, RAID_ALERT_COOLDOWN, YOUNG_ACCOUNT_DAYS
)

def is_safe_to_restore_role(role: disnake.Role, bot_top_role: disnake.Role | None) -> bool:
    if role.is_default() or role.managed:
        return False
    if bot_top_role is not None and role >= bot_top_role:
        return False
    perms = role.permissions
    if (
        perms.administrator
        or perms.manage_guild
        or perms.manage_roles
        or perms.manage_channels
        or perms.ban_members
        or perms.kick_members
        or perms.moderate_members
    ):
        return False
    return True

class Audit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent_joins: Dict[int, deque] = {}
        self._last_raid_alert: Dict[int, float] = {}
        # Словарь для подавления спама логов при автовозврате ролей (user_id -> timestamp)
        self._restoring_members: Dict[int, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot or not message.guild:
            return

        cfg = await api.get_guild_config(str(message.guild.id))
        if cfg and cfg.get("trapChannelId") and str(message.channel.id) == str(cfg["trapChannelId"]):
            member = message.author
            if not member.guild_permissions.manage_messages and not member.guild_permissions.administrator and member.id != message.guild.owner_id:
                try:
                    await message.delete()
                except disnake.Forbidden:
                    pass

                try:
                    dm_embed = disnake.Embed(
                        title="⛔ Вы были исключены с сервера",
                        description=f"Вы нарушили правило канала **#{message.channel.name}** на сервере **{message.guild.name}**, в котором запрещено писать.",
                        color=COMBAT_RED
                    )
                    dm_embed.set_footer(text=UNIFIED_FOOTER)
                    await member.send(embed=dm_embed)
                except disnake.Forbidden:
                    pass

                try:
                    await member.kick(reason=f"Сообщение в канале тишины #{message.channel.name}")
                    log_embed = disnake.Embed(
                        title="🚨 Исключение (Канал тишины)",
                        description=f"Участник {member.mention} (`{member.id}`) написал сообщение в канале {message.channel.mention} и был исключён.",
                        color=COMBAT_RED,
                        timestamp=disnake.utils.utcnow()
                    )
                    log_embed.set_footer(text=UNIFIED_FOOTER)
                    await send_log(message.guild, log_embed)
                except disnake.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: disnake.Message):
        if message.author.bot or not message.guild:
            return

        embed = disnake.Embed(
            title="🗑️ Сообщение удалено",
            description=f"**Автор:** {message.author.mention} (`{message.author.id}`)\n**Канал:** {message.channel.mention}",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
        )
        content_text = message.content[:1024] if message.content else "*Сообщение было пустым или содержало только файлы*"
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
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: disnake.Message, after: disnake.Message):
        if after.author.bot or not after.guild or before.content == after.content:
            return

        old_content = before.content if before.content else "*[Не сохранено в кэше]*"
        new_content = after.content if after.content else "*[Пустое сообщение]*"

        embed = disnake.Embed(
            title="✏️ Сообщение отредактировано",
            description=f"**Автор:** {after.author.mention} (`{after.author.id}`)\n**Канал:** {after.channel.mention} ([Перейти к сообщению]({after.jump_url}))",
            color=AIGIS_GOLD,
            timestamp=disnake.utils.utcnow()
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
            description=f"**Канал:** <#{payload.channel_id}>\n**ID сообщения:** `{payload.message_id}`\n*Текст неизвестен: сообщение было отправлено до запуска бота.*",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
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
            description=f"**Автор:** <@{author.get('id', 0)}>\n**Канал:** <#{payload.channel_id}>\n**ID сообщения:** `{payload.message_id}`",
            color=AIGIS_GOLD,
            timestamp=disnake.utils.utcnow()
        )
        embed.add_field(name="Новый текст:", value=(data.get("content") or "*Пусто*")[:1000], inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member):
        now = time.time()
        for g_id in list(self._recent_joins.keys()):
            q = self._recent_joins[g_id]
            while q and now - q[0] > RAID_WINDOW_SECONDS:
                q.popleft()
            if not q and g_id != member.guild.id:
                del self._recent_joins[g_id]

        joins = self._recent_joins.setdefault(member.guild.id, deque())
        joins.append(now)

        age_days = (disnake.utils.utcnow() - member.created_at).days
        young = age_days < YOUNG_ACCOUNT_DAYS

        # Безопасный и пакетный автовозврат сохраненных ролей
        restored_roles: List[disnake.Role] = []
        if not member.bot:
            profile = await api.get_user_profile(str(member.guild.id), str(member.id))
            cfg = await api.get_guild_config(str(member.guild.id)) or {}
            if profile:
                saved_role_ids = set(str(r) for r in (profile.get("roles") or []))
                if profile.get("isVerified") and cfg.get("verificationRoleId"):
                    saved_role_ids.add(str(cfg["verificationRoleId"]))

                bot_top_role = member.guild.me.top_role if member.guild.me else None
                roles_to_add: List[disnake.Role] = []
                for r_id in saved_role_ids:
                    if not r_id.isdigit():
                        continue
                    role = member.guild.get_role(int(r_id))
                    if role and role not in member.roles and is_safe_to_restore_role(role, bot_top_role):
                        roles_to_add.append(role)

                if roles_to_add:
                    try:
                        # Запоминаем участника: глушим спам в логах на 4 секунды
                        self._restoring_members[member.id] = time.time()
                        await member.add_roles(*roles_to_add, reason="Автовосстановление ролей из базы")
                        restored_roles = roles_to_add
                    except disnake.HTTPException:
                        self._restoring_members.pop(member.id, None)

        embed = disnake.Embed(
            title="📥 Новый участник на сервере",
            description=f"**Участник:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`",
            color=COMBAT_RED if young else TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Возраст аккаунта", value=f"{age_days} дн." + (" ⚠️ **новый аккаунт**" if young else ""), inline=True)
        if restored_roles:
            embed.add_field(
                name="♻️ Восстановлены роли из БД",
                value=", ".join(r.mention for r in restored_roles)[:1024],
                inline=False
            )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(member.guild, embed)

        # Очистка старых записей из словаря подавления
        current_time = time.time()
        for u_id, t in list(self._restoring_members.items()):
            if current_time - t > 10:
                self._restoring_members.pop(u_id, None)

        if len(joins) >= RAID_JOIN_THRESHOLD and now - self._last_raid_alert.get(member.guild.id, 0) > RAID_ALERT_COOLDOWN:
            self._last_raid_alert[member.guild.id] = now
            alert = disnake.Embed(
                title="🚨 ВОЗМОЖНЫЙ РЕЙД",
                description=f"За последние **{RAID_WINDOW_SECONDS} сек.** на сервер зашло **{len(joins)}** участников.\nРекомендуется заблокировать каналы командой `/lock`.",
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow()
            )
            alert.set_footer(text=UNIFIED_FOOTER)
            await send_log(member.guild, alert)

    @commands.Cog.listener()
    async def on_member_remove(self, member: disnake.Member):
        embed = disnake.Embed(
            title="🚪 Участник покинул сервер",
            description=f"**Участник:** {member.mention} (`{member.name}`)\n**ID:** `{member.id}`",
            color=disnake.Color.dark_grey(),
            timestamp=disnake.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: disnake.Member, after: disnake.Member):
        if after.bot:
            return

        if before.nick != after.nick:
            old_nick = before.nick or before.name
            new_nick = after.nick or after.name
            embed = disnake.Embed(
                title="📝 Изменение никнейма",
                description=f"**Участник:** {after.mention} (`{after.id}`)",
                color=AIGIS_GOLD,
                timestamp=disnake.utils.utcnow()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Было:", value=f"`{old_nick}`", inline=True)
            embed.add_field(name="Стало:", value=f"`{new_nick}`", inline=True)
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(after.guild, embed)

        if before.roles != after.roles:
            added_roles = [r for r in after.roles if r not in before.roles and not r.is_default()]
            removed_roles = [r for r in before.roles if r not in after.roles and not r.is_default()]
            if added_roles or removed_roles:
                # В PostgreSQL сохраняем всегда
                await api.update_user_roles_batch(
                    str(after.guild.id),
                    str(after.id),
                    [str(r.id) for r in added_roles],
                    [str(r.id) for r in removed_roles]
                )

                # Если роли выданы ботом при автовозврате — НЕ дублируем лог
                restore_time = self._restoring_members.get(after.id)
                if restore_time and (time.time() - restore_time) < 4.0:
                    return

                embed = disnake.Embed(
                    title="🎭 Изменение ролей участника",
                    description=f"**Участник:** {after.mention} (`{after.id}`)",
                    color=P3_BLUE,
                    timestamp=disnake.utils.utcnow()
                )
                embed.set_thumbnail(url=after.display_avatar.url)
                if added_roles:
                    embed.add_field(name="🟢 Выданы:", value=", ".join([r.mention for r in added_roles])[:1024], inline=False)
                if removed_roles:
                    embed.add_field(name="🔴 Сняты:", value=", ".join([r.mention for r in removed_roles])[:1024], inline=False)
                embed.set_footer(text=UNIFIED_FOOTER)
                await send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        if member.bot or before.channel == after.channel:
            return

        if before.channel is None and after.channel is not None:
            embed = disnake.Embed(
                title="🔊 Подключение к голосовому каналу",
                description=f"**Участник:** {member.mention} (`{member.id}`)\n**Канал:** {after.channel.mention}",
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow()
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(member.guild, embed)

        elif before.channel is not None and after.channel is None:
            embed = disnake.Embed(
                title="🔇 Отключение от голосового канала",
                description=f"**Участник:** {member.mention} (`{member.id}`)\n**Канал:** {before.channel.mention}",
                color=disnake.Color.dark_grey(),
                timestamp=disnake.utils.utcnow()
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(member.guild, embed)

        elif before.channel is not None and after.channel is not None:
            embed = disnake.Embed(
                title="🔀 Смена голосового канала",
                description=f"**Участник:** {member.mention} (`{member.id}`)\n**Из:** `#{before.channel.name}` ➔ **В:** {after.channel.mention}",
                color=AIGIS_GOLD,
                timestamp=disnake.utils.utcnow()
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: disnake.abc.GuildChannel):
        c_type = "💬 Текстовый" if isinstance(channel, disnake.TextChannel) else "🔊 Голосовой" if isinstance(channel, disnake.VoiceChannel) else "📁 Категория"
        embed = disnake.Embed(
            title="📁 Создан новый канал",
            description=f"**Канал:** {channel.mention} (`#{channel.name}`)\n**Тип:** {c_type}",
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow()
        )
        if channel.category:
            embed.add_field(name="Категория:", value=f"`{channel.category.name}`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: disnake.abc.GuildChannel):
        c_type = "💬 Текстовый" if isinstance(channel, disnake.TextChannel) else "🔊 Голосовой" if isinstance(channel, disnake.VoiceChannel) else "📁 Категория"
        embed = disnake.Embed(
            title="🗑️ Канал удален",
            description=f"**Название:** `#{channel.name}`\n**Тип:** {c_type}",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: disnake.abc.GuildChannel, after: disnake.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"• **Переименование:** `#{before.name}` ➔ `#{after.name}`")
        if isinstance(before, disnake.TextChannel) and isinstance(after, disnake.TextChannel):
            if before.topic != after.topic:
                old_t = before.topic or "*Отсутствует*"
                new_t = after.topic or "*Отсутствует*"
                changes.append(f"• **Тема канала:** `{old_t}` ➔ `{new_t}`")

        if not changes:
            return

        embed = disnake.Embed(
            title="⚙️ Параметры канала изменены",
            description=f"**Канал:** {after.mention}\n\n" + "\n".join(changes),
            color=AIGIS_GOLD,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: disnake.Role):
        embed = disnake.Embed(
            title="✨ Создана новая роль",
            description=f"**Роль:** {role.mention} (`{role.name}`)\n**Цвет:** `{str(role.color)}`",
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: disnake.Role):
        embed = disnake.Embed(
            title="🔥 Роль сервера удалена",
            description=f"**Бывшее название:** `{role.name}`\n**ID роли:** `{role.id}`",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(role.guild, embed)

def setup(bot: commands.Bot):
    bot.add_cog(Audit(bot))