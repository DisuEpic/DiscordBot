import asyncio
import datetime

import disnake
from disnake.ext import commands

from api import api
from config import ACCENT_GOLD, COMBAT_RED, GUILD_ONLY, TACTICAL_GREEN, UNIFIED_FOOTER
from utils import check_moderation_target, send_log


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock_guard = asyncio.Lock()
        self._locked_roles: dict[int, tuple[int, bool | None]] = {}

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="модерация",
        description="Команды модерации",
    )
    async def moderation(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @moderation.sub_command(
        name="закрыть",
        description="Заблокировать канал для отправки сообщений",
    )
    @commands.has_permissions(manage_channels=True)
    async def lock_channel(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        channel = inter.channel

        guild_config = await api.get_guild_config(str(inter.guild_id)) or {}
        role_id = (guild_config.get("security") or {}).get("verificationRoleId")
        target_role = (
            inter.guild.get_role(int(role_id)) if role_id else None
        ) or inter.guild.default_role

        try:
            async with self._lock_guard:
                if channel.id not in self._locked_roles:
                    overwrite = channel.overwrites_for(target_role)
                    previous = overwrite.send_messages
                    overwrite.send_messages = False
                    await channel.set_permissions(
                        target_role,
                        overwrite=overwrite,
                        reason=f"Lockdown by {inter.author}",
                    )
                    self._locked_roles[channel.id] = (target_role.id, previous)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для изменения разрешений этого канала."
            )
            return

        await inter.edit_original_response(
            content=f"🔒 Отправка сообщений для роли {target_role.mention} в {channel.mention} запрещена."
        )
        embed = disnake.Embed(
            title="🔒 Канал заблокирован",
            description=(
                f"**Канал:** {channel.mention}\n"
                f"**Модератор:** {inter.author.mention}"
            ),
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, embed)

    @moderation.sub_command(
        name="открыть",
        description="Разблокировать канал для отправки сообщений",
    )
    @commands.has_permissions(manage_channels=True)
    async def unlock_channel(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        channel = inter.channel

        try:
            async with self._lock_guard:
                saved = self._locked_roles.get(channel.id)
                locked_role = inter.guild.get_role(saved[0]) if saved else None
                if saved is None or locked_role is None:
                    await inter.edit_original_response(
                        content="Нет сохранённого состояния блокировки. Проверь права канала в Discord."
                    )
                    return

                overwrite = channel.overwrites_for(locked_role)
                overwrite.send_messages = saved[1]
                await channel.set_permissions(
                    locked_role,
                    overwrite=None if overwrite.is_empty() else overwrite,
                    reason=f"Unlocked by {inter.author}",
                )
                self._locked_roles.pop(channel.id, None)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для изменения разрешений этого канала."
            )
            return

        await inter.edit_original_response(
            content=f"🔓 Прежнее разрешение на отправку сообщений в {channel.mention} восстановлено."
        )
        embed = disnake.Embed(
            title="🔓 Блокировка канала снята",
            description=(
                f"**Канал:** {channel.mention}\n"
                f"**Модератор:** {inter.author.mention}"
            ),
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, embed)

    @moderation.sub_command(
        name="медленный_режим",
        description="Установить задержку отправки сообщений",
    )
    @commands.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        inter: disnake.ApplicationCommandInteraction,
        seconds: int = commands.Param(
            name="секунды",
            description="Задержка в секундах (0 для отключения)",
            ge=0,
            le=21600,
        ),
    ):
        await inter.response.defer(ephemeral=True)
        try:
            await inter.channel.edit(slowmode_delay=seconds)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для управления этим каналом."
            )
            return

        message = (
            "⚡ Медленный режим отключён."
            if seconds == 0
            else f"⏳ Медленный режим: **1 сообщение в {seconds} сек.**"
        )
        await inter.edit_original_response(content=message)

    @moderation.sub_command(
        name="мут",
        description="Временно заглушить участника",
    )
    @commands.has_guild_permissions(moderate_members=True)
    async def timeout(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(
            name="участник", description="Кого заглушить"
        ),
        minutes: int = commands.Param(
            name="минуты", description="Длительность (минуты)", ge=1, le=40320
        ),
        reason: str = commands.Param(
            name="причина",
            default="Нарушение правил сервера",
            description="Причина",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error)
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(
                duration=duration,
                reason=f"{reason} (Модератор: {inter.author})",
            )
            await inter.edit_original_response(
                content=f"🔇 {member.mention} отправлен в таймаут на **{minutes} мин.**\nПричина: *{reason}*"
            )
            embed = disnake.Embed(
                title="🔇 Применён таймаут",
                description=(
                    f"**Нарушитель:** {member.mention} (\`{member.id}\`)\n"
                    f"**Модератор:** {inter.author.mention}\n"
                    f"**Время:** {minutes} мин.\n"
                    f"**Причина:** {reason}"
                ),
                color=ACCENT_GOLD,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, embed)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для таймаута этого участника."
            )

    @moderation.sub_command(
        name="кик",
        description="Исключить участника с сервера",
    )
    @commands.has_guild_permissions(kick_members=True)
    async def kick(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(
            name="участник", description="Кого исключить"
        ),
        reason: str = commands.Param(
            name="причина", default="Исключён модератором", description="Причина"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error)
            return

        try:
            await member.kick(reason=f"{reason} (Модератор: {inter.author})")
            await inter.edit_original_response(
                content=f"👢 **{member.display_name}** исключён с сервера.\nПричина: *{reason}*"
            )
            embed = disnake.Embed(
                title="👢 Участник исключён",
                description=(
                    f"**Исключён:** {member.mention} (\`{member.id}\`)\n"
                    f"**Модератор:** {inter.author.mention}\n"
                    f"**Причина:** {reason}"
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, embed)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для исключения этого участника."
            )

    @moderation.sub_command(
        name="бан",
        description="Заблокировать участника на сервере",
    )
    @commands.has_guild_permissions(ban_members=True)
    async def ban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(
            name="участник", description="Нарушитель"
        ),
        reason: str = commands.Param(
            name="причина", default="Грубое нарушение правил", description="Причина"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error)
            return

        try:
            await member.ban(
                reason=f"{reason} (Модератор: {inter.author})",
                clean_history_duration=86400,
            )
            await inter.edit_original_response(
                content=f"🔨 **{member.display_name}** заблокирован на сервере.\nПричина: *{reason}*"
            )
            embed = disnake.Embed(
                title="🔨 Участник заблокирован",
                description=(
                    f"**Заблокирован:** {member.mention} (\`{member.id}\`)\n"
                    f"**Модератор:** {inter.author.mention}\n"
                    f"**Причина:** {reason}"
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, embed)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав для блокировки этого участника."
            )

    @moderation.sub_command(
        name="разбан",
        description="Разблокировать пользователя по Discord ID",
    )
    @commands.has_guild_permissions(ban_members=True)
    async def unban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_id: str = commands.Param(
            name="пользователь_id", description="Discord ID заблокированного пользователя"
        ),
        reason: str = commands.Param(
            name="причина", default="Амнистия / Разбан", description="Причина"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if not user_id.strip().isdigit():
            await inter.edit_original_response(
                content="❌ Указан некорректный Discord ID."
            )
            return

        try:
            user = await self.bot.fetch_user(int(user_id.strip()))
            await inter.guild.unban(
                user, reason=f"{reason} (Модератор: {inter.author})"
            )
            await inter.edit_original_response(
                content=f"🔓 Пользователь **{user.name}** (\`{user.id}\`) разблокирован."
            )
            embed = disnake.Embed(
                title="🔓 Пользователь разблокирован",
                description=(
                    f"**Пользователь:** {user.mention} (\`{user.id}\`)\n"
                    f"**Модератор:** {inter.author.mention}\n"
                    f"**Причина:** {reason}"
                ),
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, embed)
        except Exception as error:
            await inter.edit_original_response(
                content=f"❌ Не удалось разблокировать пользователя: {error}"
            )

    @moderation.sub_command(
        name="очистить",
        description="Очистить последние сообщения в канале",
    )
    @commands.has_permissions(manage_messages=True)
    async def clear(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(
            name="количество", description="Количество (1–100)", ge=1, le=100
        ),
    ):
        await inter.response.defer(ephemeral=True)
        cutoff = disnake.utils.utcnow() - datetime.timedelta(days=14)

        try:
            deleted = await inter.channel.purge(
                limit=amount, after=cutoff, oldest_first=False
            )
            embed = disnake.Embed(
                title="🧹 Очистка чата завершена",
                description=(
                    f"В канале {inter.channel.mention} удалено сообщений: **{len(deleted)}**.\n"
                    "*Команда обрабатывает сообщения за последние 14 дней.*"
                ),
                color=ACCENT_GOLD,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await inter.edit_original_response(embed=embed)
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота нет прав на чтение истории или удаление сообщений в этом канале."
            )
        except disnake.HTTPException as error:
            await inter.edit_original_response(
                content=f"❌ Ошибка Discord API при очистке сообщений: {error}"
            )


def setup(bot: commands.Bot):
    bot.add_cog(Moderation(bot))