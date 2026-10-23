import datetime
import disnake
from disnake.ext import commands
from utils import check_moderation_target, send_log
from config import GUILD_ONLY, AIGIS_GOLD, COMBAT_RED, TACTICAL_GREEN, UNIFIED_FOOTER

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(contexts=GUILD_ONLY, name="lock", description="Заблокировать канал для отправки сообщений")
    @commands.default_member_permissions(manage_channels=True)
    async def lock_channel(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        channel = inter.channel
        from api import api
        guild_config = await api.get_guild_config(str(inter.guild_id)) or {}
        role_id = guild_config.get("verificationRoleId")
        target_role = (inter.guild.get_role(int(role_id)) if role_id else None) or inter.guild.default_role

        try:
            await channel.set_permissions(target_role, send_messages=False, reason=f"Lockdown by {inter.author}")
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота недостаточно прав для изменения разрешений этого канала.")
            return

        await inter.edit_original_response(content=f"🔒 Сектор {channel.mention} заблокирован! Участники не могут писать.")
        embed = disnake.Embed(
            title="🔒 Сектор переведен в режим блокировки",
            description=f"Канал {channel.mention} заблокирован оператором {inter.author.mention}.",
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="unlock", description="Разблокировать канал для отправки сообщений")
    @commands.default_member_permissions(manage_channels=True)
    async def unlock_channel(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        channel = inter.channel
        from api import api
        guild_config = await api.get_guild_config(str(inter.guild_id)) or {}
        role_id = guild_config.get("verificationRoleId")
        target_role = (inter.guild.get_role(int(role_id)) if role_id else None) or inter.guild.default_role

        try:
            await channel.set_permissions(target_role, send_messages=None, reason=f"Unlocked by {inter.author}")
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота недостаточно прав для изменения разрешений этого канала.")
            return

        await inter.edit_original_response(content=f"🔓 Сектор {channel.mention} разблокирован для общения.")
        embed = disnake.Embed(
            title="🔓 Сектор разблокирован",
            description=f"Канал {channel.mention} открыт оператором {inter.author.mention}.",
            color=TACTICAL_GREEN,
            timestamp=disnake.utils.utcnow()
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="slowmode", description="Установить задержку отправки сообщений")
    @commands.default_member_permissions(manage_channels=True)
    async def slowmode(
        self,
        inter: disnake.ApplicationCommandInteraction,
        seconds: int = commands.Param(description="Задержка в секундах (0 для отключения)", ge=0, le=21600)
    ):
        await inter.response.defer(ephemeral=True)
        try:
            await inter.channel.edit(slowmode_delay=seconds)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота недостаточно прав для управления этим каналом.")
            return

        msg = "⚡ Медленный режим отключен." if seconds == 0 else f"⏳ Медленный режим установлен: **1 сообщение в {seconds} сек.**"
        await inter.edit_original_response(content=msg)

    @commands.slash_command(contexts=GUILD_ONLY, name="timeout", description="Временно заглушить участника")
    @commands.default_member_permissions(moderate_members=True)
    async def timeout(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Кого заглушить"),
        minutes: int = commands.Param(description="Длительность (минуты)", ge=1, le=40320),
        reason: str = commands.Param(default="Нарушение правил сервера", description="Причина")
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error_msg)
            return

        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration=duration, reason=f"{reason} (Модератор: {inter.author})")
            await inter.edit_original_response(content=f"🔇 Участник {member.mention} отправлен в таймаут на **{minutes} мин.**\nПричина: *{reason}*")

            log_embed = disnake.Embed(
                title="🔇 Применен таймаут",
                description=f"**Нарушитель:** {member.mention} (`{member.id}`)\n**Модератор:** {inter.author.mention}\n**Время:** {minutes} мин.\n**Причина:** {reason}",
                color=AIGIS_GOLD,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота недостаточно прав для таймаута этого участника.")

    @commands.slash_command(contexts=GUILD_ONLY, name="kick", description="Исключить участника с сервера")
    @commands.default_member_permissions(kick_members=True)
    async def kick(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Кого выгнать"),
        reason: str = commands.Param(default="Исключен модератором", description="Причина")
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error_msg)
            return

        try:
            await member.kick(reason=f"{reason} (Модератор: {inter.author})")
            await inter.edit_original_response(content=f"👢 Участник **{member.display_name}** исключен с сервера.\nПричина: *{reason}*")

            log_embed = disnake.Embed(
                title="👢 Участник исключен (Кик)",
                description=f"**Исключен:** {member.mention} (`{member.id}`)\n**Модератор:** {inter.author.mention}\n**Причина:** {reason}",
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота не хватает прав для исключения этого участника.")

    @commands.slash_command(contexts=GUILD_ONLY, name="ban", description="Заблокировать участника на сервере")
    @commands.default_member_permissions(ban_members=True)
    async def ban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="Нарушитель"),
        reason: str = commands.Param(default="Грубое нарушение правил", description="Причина")
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error_msg)
            return

        try:
            await member.ban(reason=f"{reason} (Модератор: {inter.author})", clean_history_duration=86400)
            await inter.edit_original_response(content=f"🔨 Участник **{member.display_name}** успешно заблокирован на сервере.\nПричина: *{reason}*")

            log_embed = disnake.Embed(
                title="🔨 Допуск аннулирован (Бан)",
                description=f"**Забанен:** {member.mention} (`{member.id}`)\n**Модератор:** {inter.author.mention}\n**Причина:** {reason}",
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ Ошибка прав при блокировке участника.")

    @commands.slash_command(contexts=GUILD_ONLY, name="unban", description="Разблокировать пользователя по Discord ID")
    @commands.default_member_permissions(ban_members=True)
    async def unban(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_id: str = commands.Param(description="Discord ID забаненного пользователя"),
        reason: str = commands.Param(default="Амнистия / Разбан", description="Причина")
    ):
        await inter.response.defer(ephemeral=True)
        if not user_id.strip().isdigit():
            await inter.edit_original_response(content="❌ Указан некорректный Discord ID.")
            return

        try:
            user = await self.bot.fetch_user(int(user_id.strip()))
            await inter.guild.unban(user, reason=f"{reason} (Модератор: {inter.author})")
            await inter.edit_original_response(content=f"🔓 Пользователь **{user.name}** (`{user_id}`) успешно разблокирован!")

            log_embed = disnake.Embed(
                title="🔓 Пользователь разблокирован (Unban)",
                description=f"**Пользователь:** {user.mention} (`{user.id}`)\n**Модератор:** {inter.author.mention}\n**Причина:** {reason}",
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)
        except Exception as e:
            await inter.edit_original_response(content=f"❌ Не удалось разблокировать пользователя: {e}")

    @commands.slash_command(contexts=GUILD_ONLY, name="clear", description="Очистить сообщения в канале")
    @commands.default_member_permissions(manage_messages=True)
    async def clear(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(description="Количество (1-100)", ge=1, le=100)
    ):
        await inter.response.defer(ephemeral=True)
        cutoff = disnake.utils.utcnow() - datetime.timedelta(days=14)
        try:
            deleted = await inter.channel.purge(limit=amount, after=cutoff)
            embed = disnake.Embed(
                title="🧹 Очистка сектора завершена",
                description=f"В секторе {inter.channel.mention} удалено сообщений: **{len(deleted)}** шт.\n*(Сообщения старше 14 дней не затрагиваются)*",
                color=AIGIS_GOLD
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await inter.edit_original_response(embed=embed)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота нет прав на чтение истории или удаление сообщений в этом канале.")
        except disnake.HTTPException as e:
            await inter.edit_original_response(content=f"❌ Ошибка Discord API при очистке сообщений: {e}")

def setup(bot: commands.Bot):
    bot.add_cog(Moderation(bot))