import time
import disnake
from disnake.ext import commands
from typing import Optional
from api import api
from views import SettingsDashboardView
from config import (
    GUILD_ONLY, P3_BLUE, COMBAT_RED, TACTICAL_GREEN,
    UNIFIED_FOOTER, VERIFY_TIMEOUT_MINUTES
)

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(contexts=GUILD_ONLY, name="setup_config", description="Настроить каналы и роль верификации")
    @commands.default_member_permissions(administrator=True)
    async def setup_config(
        self,
        inter: disnake.ApplicationCommandInteraction,
        verification_role: Optional[disnake.Role] = None,
        welcome_channel: Optional[disnake.TextChannel] = None,
        log_channel: Optional[disnake.TextChannel] = None
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        existing = await api.get_guild_config(guild_id) or {}
        payload = {
            "guildId": guild_id,
            "verificationRoleId": str(verification_role.id) if verification_role else existing.get("verificationRoleId"),
            "welcomeChannelId": str(welcome_channel.id) if welcome_channel else existing.get("welcomeChannelId"),
            "logChannelId": str(log_channel.id) if log_channel else existing.get("logChannelId"),
            "trapChannelId": existing.get("trapChannelId")
        }

        if await api.save_guild_config(payload):
            embed = disnake.Embed(title="⚙️ Конфигурация сервера успешно сохранена!", color=TACTICAL_GREEN)
            embed.add_field(name="Роль верификации", value=f"<@&{payload['verificationRoleId']}>" if payload["verificationRoleId"] else "Не задана", inline=False)
            embed.add_field(name="Канал приветствий", value=f"<#{payload['welcomeChannelId']}>" if payload["welcomeChannelId"] else "Не задан", inline=False)
            embed.add_field(name="Канал аудита (логов)", value=f"<#{payload['logChannelId']}>" if payload["logChannelId"] else "Не задан", inline=False)
            embed.set_footer(text=UNIFIED_FOOTER)
            await inter.edit_original_response(embed=embed)
        else:
            await inter.edit_original_response(content="❌ Ошибка при сохранении в API бэкенда.")

    @commands.slash_command(contexts=GUILD_ONLY, name="setup_trap_channel", description="Назначить канал тишины (кик за сообщение)")
    @commands.default_member_permissions(administrator=True)
    async def setup_trap_channel(self, inter: disnake.ApplicationCommandInteraction, channel: disnake.TextChannel):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        existing = await api.get_guild_config(guild_id) or {}
        existing["guildId"] = guild_id
        existing["trapChannelId"] = str(channel.id)

        if await api.save_guild_config(existing):
            await inter.edit_original_response(content=f"🤫 Канал тишины установлен: {channel.mention}. Любое сообщение удаляется, а автор исключается.")
        else:
            await inter.edit_original_response(content="❌ Ошибка сохранения параметров.")

    @commands.slash_command(contexts=GUILD_ONLY, name="settings", description="Посмотреть текущие настройки Aigis и управлять ими")
    @commands.default_member_permissions(administrator=True)
    async def settings(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)

        cfg = await api.get_guild_config(guild_id) or {}
        all_roles = await api.get_roles(str(inter.guild_id))
        guild_roles = [r for r in all_roles if str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))]

        v_role = f"<@&{cfg['verificationRoleId']}>" if cfg.get("verificationRoleId") else "🔴 Не настроена"
        w_chan = f"<#{cfg['welcomeChannelId']}>" if cfg.get("welcomeChannelId") else "⚪ Отключен"
        l_chan = f"<#{cfg['logChannelId']}>" if cfg.get("logChannelId") else "⚪ Отключен"
        t_chan = f"<#{cfg['trapChannelId']}> (Кик за сообщение)" if cfg.get("trapChannelId") else "⚪ Отключен"

        categories_set = set(r.get("category") or "Общие" for r in guild_roles)
        roles_info = f"Всего: **{len(guild_roles)}** шт. в категориях: {', '.join(f'`{c}`' for c in categories_set)}" if guild_roles else "⚪ Роли не добавлены"

        embed = disnake.Embed(
            title="⚙️ Центр управления Aigis • 7-е Поколение",
            description=f"Текущая конфигурация защитного периметра сервера **{inter.guild.name}**:",
            color=P3_BLUE
        )
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)

        embed.add_field(name="🛡️ Роль верификации", value=v_role, inline=False)
        embed.add_field(name="👋 Канал приветствий", value=w_chan, inline=False)
        embed.add_field(name="📜 Канал аудита (логов)", value=l_chan, inline=False)
        embed.add_field(name="🤫 Канал-ловушка (Тишина)", value=t_chan, inline=False)
        embed.add_field(name="⏱️ Таймер автокика новичков", value=f"`{VERIFY_TIMEOUT_MINUTES} минут`", inline=False)
        embed.add_field(name="🎭 Роли для выбора (в базе)", value=roles_info, inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = SettingsDashboardView(author_id=inter.author.id)
        await inter.edit_original_response(embed=embed, view=view)

    @commands.slash_command(contexts=GUILD_ONLY, name="overdrive_mode", description="🔥 Активировать боевой режим перегрузки Aigis")
    @commands.default_member_permissions(administrator=True)
    async def overdrive_mode(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        embed = disnake.Embed(
            title="⚠️ РЕЖИМ «ПЕРЕГРУЗКА» АКТИВИРОВАН (OVERDRIVE MODE)",
            description=(
                "**[ОГРАНИЧИТЕЛИ СНЯТЫ]**\n"
                "Все системы охлаждения отключены. Редукторы мощности переведены на 120%!\n"
                "Папиллонное сердце работает на пиковой частоте. Боевая готовность: **МАКСИМАЛЬНАЯ**."
            ),
            color=COMBAT_RED
        )
        embed.add_field(name="🔋 Энергия ядра", value="`120% (Overdrive)`", inline=True)
        embed.add_field(name="🌡️ Температура приводов", value="`850°C (Критическая)`", inline=True)
        embed.add_field(name="🎯 Скорость реакции", value="`0.01 ms`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="scan", description="🔍 Тактическое сканирование субъекта")
    async def scan(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(default=None, description="Кого сканировать")
    ):
        target = member or inter.author
        await inter.response.defer()

        persona_sync = (target.id % 60) + 40
        threat_level = "🟢 Минимальный (Союзник)" if not target.guild_permissions.administrator else "👑 Высший (Командующий)"

        embed = disnake.Embed(
            title=f"🔍 Тактический анализ субъекта: {target.display_name}",
            description="Отчет визуальных и телеметрических сенсоров Aigis:",
            color=P3_BLUE
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Идентификатор (ID)", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Уровень угрозы", value=threat_level, inline=True)
        embed.add_field(name="Синхронизация с Персоной", value=f"`{persona_sync}%`", inline=True)
        embed.add_field(name="Интеграция в периметр", value=target.joined_at.strftime("%d.%m.%Y") if target.joined_at else "N/A", inline=True)
        embed.add_field(name="Создание профиля", value=target.created_at.strftime("%d.%m.%Y"), inline=True)
        embed.add_field(name="Активные роли", value=f"**{len(target.roles) - 1}** шт.", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="ping", description="Диагностика Папиллонного сердца и задержки связи")
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        start_time = time.time()
        backend_ok = await api.health()
        backend_time = round((time.time() - start_time) * 1000)
        backend_status = "🟢 В норме" if backend_ok else "🔴 Сбой связи"
        discord_ping = round(self.bot.latency * 1000)

        embed = disnake.Embed(
            title="🤖 Диагностика боевых систем Aigis",
            description="Телеметрия аппаратных модулей и нейронной связи:",
            color=P3_BLUE
        )
        embed.add_field(name="📡 Шлюз Discord (Задержка)", value=f"`{discord_ping} ms`", inline=True)
        embed.add_field(name="💾 База данных C# (Отклик)", value=f"`{backend_time} ms` ({backend_status})", inline=True)
        embed.add_field(name="❤️ Папиллонное сердце", value="`Стабильно`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="server_info", description="Тактический отчет о состоянии сервера")
    async def server_info(self, inter: disnake.ApplicationCommandInteraction):
        guild = inter.guild
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        created_at = guild.created_at.strftime("%d.%m.%Y")

        embed = disnake.Embed(
            title=f"📊 Тактический статус: {guild.name}",
            description="Сводка данных по защищаемому периметру:",
            color=P3_BLUE
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Командующий", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="📅 Дата основания", value=created_at, inline=True)
        embed.add_field(name="👥 Контингент", value=f"Всего: **{guild.member_count}**\n(Людей: {humans} | Ботов: {bots})", inline=True)
        embed.add_field(name="💬 Каналы связи", value=f"Текст: {len(guild.text_channels)} | Голос: {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="🎭 Сигнатуры ролей", value=f"Всего: **{len(guild.roles)}**", inline=True)
        embed.add_field(name="🛡️ Уровень защиты", value=str(guild.verification_level).capitalize(), inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="avatar", description="Сканирование визуального идентификатора (Аватар)")
    async def avatar(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(default=None, description="Кого проверить")
    ):
        target = member or inter.author
        avatar_url = target.display_avatar.url

        embed = disnake.Embed(
            title=f"🔍 Визуальный идентификатор: {target.display_name}",
            description=f"[Скачать аватар в оригинале]({avatar_url})",
            color=P3_BLUE
        )
        embed.set_image(url=avatar_url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="user_profile", description="Посмотреть профиль пользователя в C# базе данных")
    @commands.default_member_permissions(administrator=True)
    async def user_profile(self, inter: disnake.ApplicationCommandInteraction, member: Optional[disnake.Member] = None):
        await inter.response.defer(ephemeral=True)
        target = member or inter.author

        user_data = await api.get_user_profile(str(inter.guild_id), str(target.id))
        if not user_data:
            await inter.edit_original_response(content=f"Субъект {target.mention} еще не зарегистрирован в базе.")
            return

        embed = disnake.Embed(title=f"📋 Личное дело: {target.display_name}", color=P3_BLUE)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Идентификатор", value=f"`{user_data.get('discordId')}`", inline=True)
        embed.add_field(name="Статус верификации", value="✅ Подтвержден" if user_data.get("isVerified") else "❌ Не верифицирован", inline=True)
        roles_val = ", ".join(f"<@&{r}>" for r in user_data.get("roles", [])) or "Нет"
        embed.add_field(name="Синхронизированные роли", value=roles_val[:1024], inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)
    @commands.slash_command(contexts=GUILD_ONLY, name="test_join", description="Симитировать вход участника для теста возврата ролей")
    @commands.default_member_permissions(administrator=True)
    async def test_join(self, inter: disnake.ApplicationCommandInteraction, member: Optional[disnake.Member] = None):
        await inter.response.defer(ephemeral=True)
        target = member or inter.author
        audit_cog = self.bot.get_cog("Audit")
        if audit_cog:
            await audit_cog.on_member_join(target)
            await inter.edit_original_response(content=f"✅ Симуляция входа для {target.mention} выполнена! Проверь роли и канал логов.")
def setup(bot: commands.Bot):
    bot.add_cog(Utility(bot))