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

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="setup_config",
        description="Единая настройка каналов, верификации, ловушки и приватных войсов"
    )
    @commands.default_member_permissions(administrator=True)
    async def setup_config(
        self,
        inter: disnake.ApplicationCommandInteraction,
        verification_role: Optional[disnake.Role] = commands.Param(default=None, description="Роль, выдаваемая после верификации"),
        welcome_channel: Optional[disnake.TextChannel] = commands.Param(default=None, description="Канал для карточек приветствия"),
        log_channel: Optional[disnake.TextChannel] = commands.Param(default=None, description="Канал для логов (аудита) сервера"),
        trap_channel: Optional[disnake.TextChannel] = commands.Param(default=None, description="Канал-ловушка (кик за любое сообщение)"),
        voice_hub_channel: Optional[disnake.VoiceChannel] = commands.Param(default=None, description="Голосовой канал «➕ Создать комнату»"),
        create_voice_hub: bool = commands.Param(default=False, description="Автоматически создать категорию и канал для приватных войсов?")
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        existing = await api.get_guild_config(guild_id) or {}

        target_voice_hub = voice_hub_channel
        if create_voice_hub and not target_voice_hub:
            # 1. Проверяем, есть ли уже живой канал из БД на сервере
            existing_hub_id = existing.get("voiceGeneratorChannelId")
            if existing_hub_id and str(existing_hub_id).isdigit():
                ch = inter.guild.get_channel(int(existing_hub_id))
                if isinstance(ch, disnake.VoiceChannel):
                    target_voice_hub = ch

            # 2. Проверяем, нет ли уже канала с таким именем на сервере, чтобы не дублировать
            if not target_voice_hub:
                for v_ch in inter.guild.voice_channels:
                    if v_ch.name == "➕ Создать комнату":
                        target_voice_hub = v_ch
                        break

            # 3. Создаем только если его действительно еще нет
            if not target_voice_hub:
                try:
                    category = disnake.utils.get(inter.guild.categories, name="🔊 Приватные комнаты")
                    if not category:
                        category = await inter.guild.create_category("🔊 Приватные комнаты")
                    target_voice_hub = await inter.guild.create_voice_channel("➕ Создать комнату", category=category)
                except disnake.Forbidden:
                    await inter.edit_original_response(content="⚠️ У бота недостаточно прав для автоматического создания каналов.")
                    return

        payload = {
            **existing,
            "guildId": guild_id,
            "verificationRoleId": str(verification_role.id) if verification_role else existing.get("verificationRoleId"),
            "welcomeChannelId": str(welcome_channel.id) if welcome_channel else existing.get("welcomeChannelId"),
            "logChannelId": str(log_channel.id) if log_channel else existing.get("logChannelId"),
            "trapChannelId": str(trap_channel.id) if trap_channel else existing.get("trapChannelId"),
            "voiceGeneratorChannelId": str(target_voice_hub.id) if target_voice_hub else existing.get("voiceGeneratorChannelId"),
        }

        if await api.save_guild_config(payload):
            embed = disnake.Embed(title="⚙️ Конфигурация сервера успешно сохранена!", color=TACTICAL_GREEN)
            embed.add_field(
                name="🛡️ Роль верификации",
                value=f"<@&{payload['verificationRoleId']}>" if payload.get("verificationRoleId") else "Не задана",
                inline=False
            )
            embed.add_field(
                name="👋 Канал приветствий",
                value=f"<#{payload['welcomeChannelId']}>" if payload.get("welcomeChannelId") else "Не задан",
                inline=False
            )
            embed.add_field(
                name="📜 Канал аудита (логов)",
                value=f"<#{payload['logChannelId']}>" if payload.get("logChannelId") else "Не задан",
                inline=False
            )
            embed.add_field(
                name="🔊 Создание приватных войсов",
                value=f"<#{payload['voiceGeneratorChannelId']}>" if payload.get("voiceGeneratorChannelId") else "Не задан",
                inline=False
            )
            embed.add_field(
                name="🤫 Канал-ловушка (Тишина)",
                value=f"<#{payload['trapChannelId']}>" if payload.get("trapChannelId") else "Не задан",
                inline=False
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await inter.edit_original_response(embed=embed)
        else:
            await inter.edit_original_response(content="❌ Ошибка при сохранении конфигурации в БД.")

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
        v_hub = f"<#{cfg['voiceGeneratorChannelId']}>" if cfg.get("voiceGeneratorChannelId") else "⚪ Отключен"

        categories_set = set(r.get("category") or "Общие" for r in guild_roles)
        roles_info = f"Всего: **{len(guild_roles)}** шт. в категориях: {', '.join(f'`{c}`' for c in categories_set)}" if guild_roles else "⚪ Роли не добавлены"

        embed = disnake.Embed(
            title="⚙️ Центр управления Aigis",
            description=f"Текущая конфигурация сервера **{inter.guild.name}**:",
            color=P3_BLUE
        )
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)

        embed.add_field(name="🛡️ Роль верификации", value=v_role, inline=False)
        embed.add_field(name="👋 Канал приветствий", value=w_chan, inline=False)
        embed.add_field(name="📜 Канал аудита (логов)", value=l_chan, inline=False)
        embed.add_field(name="🔊 Создание приватных войсов", value=v_hub, inline=False)
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

    @commands.slash_command(contexts=GUILD_ONLY, name="scan", description="🔍 Информация об участнике")
    async def scan(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(default=None, description="Кого проверить")
    ):
        target = member or inter.author
        await inter.response.defer()

        persona_sync = (target.id % 60) + 40
        threat_level = "🟢 Участник" if not target.guild_permissions.administrator else "👑 Администратор"

        embed = disnake.Embed(
            title=f"🔍 Информация об участнике: {target.display_name}",
            color=P3_BLUE
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Статус", value=threat_level, inline=True)
        embed.add_field(name="Синхронизация", value=f"`{persona_sync}%`", inline=True)
        embed.add_field(name="На сервере с", value=target.joined_at.strftime("%d.%m.%Y") if target.joined_at else "N/A", inline=True)
        embed.add_field(name="Аккаунт создан", value=target.created_at.strftime("%d.%m.%Y"), inline=True)
        embed.add_field(name="Роли", value=f"**{len(target.roles) - 1}** шт.", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="ping", description="Проверка пинга и состояния базы данных")
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        start_time = time.time()
        backend_ok = await api.health()
        backend_time = round((time.time() - start_time) * 1000)
        backend_status = "🟢 В норме" if backend_ok else "🔴 Сбой связи"
        discord_ping = round(self.bot.latency * 1000)

        embed = disnake.Embed(
            title="🤖 Диагностика систем Aigis",
            color=P3_BLUE
        )
        embed.add_field(name="📡 Шлюз Discord", value=f"`{discord_ping} ms`", inline=True)
        embed.add_field(name="💾 База данных C#", value=f"`{backend_time} ms` ({backend_status})", inline=True)
        embed.add_field(name="❤️ Статус", value="`Стабильно`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="server_info", description="Информация о сервере")
    async def server_info(self, inter: disnake.ApplicationCommandInteraction):
        guild = inter.guild
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        created_at = guild.created_at.strftime("%d.%m.%Y")

        embed = disnake.Embed(
            title=f"📊 Информация о сервере: {guild.name}",
            color=P3_BLUE
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Владелец", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="📅 Создан", value=created_at, inline=True)
        embed.add_field(name="👥 Участники", value=f"Всего: **{guild.member_count}**\n(Людей: {humans} | Ботов: {bots})", inline=True)
        embed.add_field(name="💬 Каналы", value=f"Текст: {len(guild.text_channels)} | Голос: {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="🎭 Роли", value=f"Всего: **{len(guild.roles)}**", inline=True)
        embed.add_field(name="🛡️ Защита", value=str(guild.verification_level).capitalize(), inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="avatar", description="Посмотреть аватар участника")
    async def avatar(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(default=None, description="Кого проверить")
    ):
        target = member or inter.author
        avatar_url = target.display_avatar.url

        embed = disnake.Embed(
            title=f"🔍 Аватар: {target.display_name}",
            description=f"[Скачать оригинал]({avatar_url})",
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
            await inter.edit_original_response(content=f"Участник {target.mention} еще не зарегистрирован в базе.")
            return

        embed = disnake.Embed(title=f"📋 Профиль в БД: {target.display_name}", color=P3_BLUE)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Discord ID", value=f"`{user_data.get('discordId')}`", inline=True)
        embed.add_field(name="Статус верификации", value="✅ Подтвержден" if user_data.get("isVerified") else "❌ Не верифицирован", inline=True)
        roles_val = ", ".join(f"<@&{r}>" for r in user_data.get("roles", [])) or "Нет"
        embed.add_field(name="Сохраненные роли", value=roles_val[:1024], inline=False)
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