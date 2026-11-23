import time
from typing import Optional

import disnake
from disnake.ext import commands

from api import api
from config import (
    GUILD_ONLY,
    BRAND_COLOR,
    TACTICAL_GREEN,
    UNIFIED_FOOTER,
    VERIFY_TIMEOUT_MINUTES,
)
from views import SettingsDashboardView


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="help",
        description="💠 Список возможностей и команд Mirei",
    )
    async def help_cmd(self, inter: disnake.ApplicationCommandInteraction):
        embed = disnake.Embed(
            title="💠 Справочный центр Mirei",
            description="Команды ИИ, модерации и настройки сервера.",
            color=BRAND_COLOR,
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(
            name="🧠 ИИ-чат",
            value=(
                "• Упомяни Mirei или ответь на её сообщение.\n"
                "• Можно приложить картинку из Discord.\n"
                "• `/ai` — выбор провайдера, автоответов, сценария и правил."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Защита, верификация и настройки",
            value=(
                "• `/setup_config` — роли, каналы, капча, автокик, ловушка и голосовые комнаты.\n"
                "• `/settings` — текущая конфигурация и сброс параметров.\n"
                "• `/send_verify_panel` и `/edit_verify_panel` — панель верификации.\n"
                "• `/set_welcome` — текст приветствия.\n"
                "• `/unverify` — сброс верификации участника."
            ),
            inline=False,
        )

        moderation_help = (
            "• `/timeout`, `/kick`, `/ban`, `/unban` — модерация участников.\n"
            "• `/clear` — очистка до 100 последних сообщений.\n"
            "• `/lock`, `/unlock`, `/slowmode` — управление чатом."
        )
        if self.bot.get_cog("AutoModeration"):
            moderation_help += "\n• `/automod set` и `/automod status` — фильтры и исключения."
        embed.add_field(name="🔨 Модерация", value=moderation_help, inline=False)

        embed.add_field(
            name="🔊 Голосовые комнаты и роли по кнопкам",
            value=(
                "• Войди в канал-генератор, чтобы создать временную комнату.\n"
                "• `/add_role`, `/delete_role`, `/send_category_panel`, "
                "`/send_all_categories`, `/edit_category_panel` — каталог и панели ролей.\n"
                "• `/give_role` и `/take_role` — ручное управление ролями."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Статистика и утилиты",
            value=(
                "• `/stats setup`, `/stats refresh`, `/stats toggle`, "
                "`/stats remove` — счётчики в каналах.\n"
                "• `/server_stats` — статистика сервера.\n"
                "• `/scan`, `/server_info`, `/avatar`, `/ping`."
            ),
            inline=False,
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="setup_config",
        description="Настроить каналы, верификацию, автокик, ловушку и временные комнаты",
    )
    @commands.default_member_permissions(administrator=True)
    async def setup_config(
        self,
        inter: disnake.ApplicationCommandInteraction,
        verification_role: Optional[disnake.Role] = commands.Param(
            default=None, description="Роль после верификации"
        ),
        welcome_channel: Optional[disnake.TextChannel] = commands.Param(
            default=None, description="Канал для карточек приветствия"
        ),
        log_channel: Optional[disnake.TextChannel] = commands.Param(
            default=None, description="Канал журнала сервера"
        ),
        trap_channel: Optional[disnake.TextChannel] = commands.Param(
            default=None, description="Канал-ловушка с исключением за отправку сообщения"
        ),
        voice_hub_channel: Optional[disnake.VoiceChannel] = commands.Param(
            default=None, description="Голосовой канал «Создать комнату»"
        ),
        voice_room_template: Optional[str] = commands.Param(
            default=None, description="Шаблон имени комнаты, например ╠ 〘🔊〙 {user}"
        ),
        create_voice_hub: bool = commands.Param(
            default=False, description="Создать канал-генератор автоматически"
        ),
        use_captcha: Optional[bool] = commands.Param(
            default=None, description="Требовать капчу у новых аккаунтов"
        ),
        auto_kick_unverified: Optional[bool] = commands.Param(
            default=None, description="Исключать новичков по истечении времени верификации"
        ),
        verify_timeout_minutes: Optional[int] = commands.Param(
            default=None,
            description="Время на верификацию в минутах",
            ge=1,
            le=1440,
        ),
    ):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)

        existing = await api.get_guild_config_for_update(guild_id)
        if existing is None:
            await inter.edit_original_response(
                content="API не вернуло настройки. Повтори попытку."
            )
            return

        security = existing.get("security") or {}
        welcome = existing.get("welcome") or {}
        voice = existing.get("voice") or {}

        target_voice_hub = voice_hub_channel
        if create_voice_hub and target_voice_hub is None:
            hub_id = str(voice.get("generatorChannelId") or "")
            if hub_id.isdecimal():
                channel = guild.get_channel(int(hub_id))
                if isinstance(channel, disnake.VoiceChannel):
                    target_voice_hub = channel

            if target_voice_hub is None:
                target_voice_hub = next(
                    (
                        channel
                        for channel in guild.voice_channels
                        if "создать комнату" in channel.name.lower()
                    ),
                    None,
                )

            if target_voice_hub is None:
                category_name = "── 〘🔊〙 Голосовые 〘🔊〙 ──"
                try:
                    category = disnake.utils.get(guild.categories, name=category_name)
                    if category is None:
                        category = await guild.create_category(category_name)
                    target_voice_hub = await guild.create_voice_channel(
                        "╔ 〘➕〙 Создать комнату", category=category
                    )
                except disnake.Forbidden:
                    await inter.edit_original_response(
                        content="⚠️ У бота недостаточно прав для создания голосового канала."
                    )
                    return

        saved = True

        if log_channel is not None:
            saved = saved and await api.update_general_config(
                guild_id, str(log_channel.id)
            )

        if any(
            value is not None
            for value in (
                verification_role,
                trap_channel,
                use_captcha,
                auto_kick_unverified,
                verify_timeout_minutes,
            )
        ):
            security_payload = {
                "verificationRoleId": (
                    str(verification_role.id)
                    if verification_role is not None
                    else security.get("verificationRoleId")
                ),
                "trapChannelId": (
                    str(trap_channel.id)
                    if trap_channel is not None
                    else security.get("trapChannelId")
                ),
                "useCaptcha": (
                    use_captcha
                    if use_captcha is not None
                    else security.get("useCaptcha", True)
                ),
                "autoKickUnverified": (
                    auto_kick_unverified
                    if auto_kick_unverified is not None
                    else security.get("autoKickUnverified", False)
                ),
                "verifyTimeoutMinutes": (
                    verify_timeout_minutes
                    if verify_timeout_minutes is not None
                    else security.get("verifyTimeoutMinutes", VERIFY_TIMEOUT_MINUTES)
                ),
            }
            saved = saved and await api.update_security_config(guild_id, security_payload)

        if welcome_channel is not None:
            welcome_payload = {
                "channelId": str(welcome_channel.id),
                "title": welcome.get("title"),
                "description": welcome.get("description"),
            }
            saved = saved and await api.update_welcome_config(guild_id, welcome_payload)

        if target_voice_hub is not None or voice_room_template is not None:
            voice_payload = {
                "generatorChannelId": (
                    str(target_voice_hub.id)
                    if target_voice_hub is not None
                    else voice.get("generatorChannelId")
                ),
                "roomTemplate": (
                    voice_room_template.strip()
                    if voice_room_template
                    else voice.get("roomTemplate")
                ),
            }
            saved = saved and await api.update_voice_config(guild_id, voice_payload)

        if not saved:
            await inter.edit_original_response(
                content=(
                    "❌ API не подтвердило сохранение всей конфигурации. "
                    "Проверь текущие значения через `/settings`."
                )
            )
            return

        config = await api.get_guild_config(guild_id) or {}
        security = config.get("security") or {}
        welcome = config.get("welcome") or {}
        voice = config.get("voice") or {}

        role = (
            f"<@&{security['verificationRoleId']}>"
            if security.get("verificationRoleId")
            else "Не задана"
        )
        captcha = "Вкл" if security.get("useCaptcha", True) else "Выкл"
        auto_kick = (
            f"Вкл ({security.get('verifyTimeoutMinutes', VERIFY_TIMEOUT_MINUTES)} мин.)"
            if security.get("autoKickUnverified")
            else "Выкл"
        )
        voice_hub = (
            f"<#{voice['generatorChannelId']}> "
            f"(шаблон: `{voice.get('roomTemplate') or 'Авто'}`)"
            if voice.get("generatorChannelId")
            else "Не задан"
        )

        embed = disnake.Embed(
            title="⚙️ Конфигурация сервера сохранена",
            color=TACTICAL_GREEN,
        )
        embed.add_field(
            name="🛡️ Верификация",
            value=f"Роль: {role}\nКапча: `{captcha}` | Автокик: `{auto_kick}`",
            inline=False,
        )
        embed.add_field(
            name="👋 Канал приветствий",
            value=f"<#{welcome['channelId']}>" if welcome.get("channelId") else "Не задан",
            inline=False,
        )
        embed.add_field(
            name="📜 Канал журнала",
            value=f"<#{config['logChannelId']}>" if config.get("logChannelId") else "Не задан",
            inline=False,
        )
        embed.add_field(name="🔊 Временные голосовые комнаты", value=voice_hub, inline=False)
        embed.add_field(
            name="🤫 Канал-ловушка",
            value=(
                f"<#{security['trapChannelId']}>"
                if security.get("trapChannelId")
                else "Не задан"
            ),
            inline=False,
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="settings",
        description="Посмотреть и изменить настройки Mirei",
    )
    @commands.default_member_permissions(administrator=True)
    async def settings(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)

        config = await api.get_guild_config(guild_id) or {}
        security = config.get("security") or {}
        welcome = config.get("welcome") or {}
        voice = config.get("voice") or {}
        ai = config.get("ai") or {}
        stats = config.get("stats") or {}

        all_roles = await api.get_roles(guild_id)
        guild_roles = [
            role
            for role in all_roles
            if str(role.get("roleId", "")).isdigit()
            and guild.get_role(int(role["roleId"]))
        ]

        verification_role = (
            f"<@&{security['verificationRoleId']}>"
            if security.get("verificationRoleId")
            else "Не настроена"
        )
        captcha = "капча включена" if security.get("useCaptcha", True) else "в 1 клик"
        auto_kick = (
            f"Включён (`{security.get('verifyTimeoutMinutes', VERIFY_TIMEOUT_MINUTES)} мин.`)"
            if security.get("autoKickUnverified")
            else "Отключён"
        )
        welcome_channel = (
            f"<#{welcome['channelId']}>" if welcome.get("channelId") else "Отключён"
        )
        log_channel = (
            f"<#{config['logChannelId']}>" if config.get("logChannelId") else "Отключён"
        )
        trap_channel = (
            f"<#{security['trapChannelId']}> (исключение за сообщение)"
            if security.get("trapChannelId")
            else "Отключён"
        )
        voice_template = voice.get("roomTemplate") or "Авто"
        voice_hub = (
            f"<#{voice['generatorChannelId']}> (шаблон: `{voice_template}`)"
            if voice.get("generatorChannelId")
            else "Отключён"
        )
        auto_reply_chance = int(ai.get("autoReplyChance") or 0)
        ai_status = (
            f"Включён | Провайдер: `{ai.get('provider') or 'auto'}` "
            f"| Автоответы: `{auto_reply_chance}%`"
            if ai.get("enabled", True)
            else "Отключён"
        )
        stats_status = (
            f"Включена (стиль: `{(stats.get('style') or 'en').upper()}`)"
            if stats.get("enabled")
            else "Отключена (`/stats setup`)"
        )

        categories = sorted({role.get("category") or "Общие" for role in guild_roles})
        roles_info = (
            f"Всего: **{len(guild_roles)}**. Категории: "
            + ", ".join(f"`{category}`" for category in categories)
            if guild_roles
            else "Роли не добавлены"
        )

        embed = disnake.Embed(
            title="💠 Центр управления Mirei",
            description=f"Настройки сервера **{guild.name}**.",
            color=BRAND_COLOR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        fields = [
            ("🛡️ Роль верификации", f"{verification_role} ({captcha})"),
            ("⏱️ Автокик новичков", auto_kick),
            ("👋 Канал приветствий", welcome_channel),
            ("📜 Канал журнала", log_channel),
            ("🔊 Временные голосовые комнаты", voice_hub),
            ("🤫 Канал-ловушка", trap_channel),
            ("📊 Счётчики статистики", stats_status),
            ("🧠 Модуль ИИ", ai_status),
            ("🎭 Роли для выбора", roles_info[:1024]),
        ]
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=UNIFIED_FOOTER)
        view = SettingsDashboardView(author_id=inter.author.id)
        await inter.edit_original_response(embed=embed, view=view)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="scan",
        description="Показать информацию об участнике",
    )
    async def scan(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(
            default=None, description="Чей профиль показать"
        ),
    ):
        target = member or inter.author
        await inter.response.defer()

        age_days = (disnake.utils.utcnow() - target.created_at).days
        status = "👑 Администратор" if target.guild_permissions.administrator else "🟢 Участник"
        top_role = target.top_role.mention if not target.top_role.is_default() else "Нет"

        embed = disnake.Embed(
            title=f"🔍 Профиль участника: {target.display_name}",
            color=BRAND_COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Статус", value=status, inline=True)
        embed.add_field(name="Высшая роль", value=top_role, inline=True)
        embed.add_field(
            name="На сервере с",
            value=target.joined_at.strftime("%d.%m.%Y") if target.joined_at else "Неизвестно",
            inline=True,
        )
        embed.add_field(
            name="Аккаунт создан",
            value=f"{target.created_at.strftime('%d.%m.%Y')} ({age_days} дн.)",
            inline=True,
        )
        embed.add_field(name="Роли", value=f"**{len(target.roles) - 1}** шт.", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ping",
        description="Проверить задержку Discord и состояние API",
    )
    async def ping(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        started = time.monotonic()
        backend_ok = await api.health()
        backend_ms = round((time.monotonic() - started) * 1000)
        backend_status = "🟢 В норме" if backend_ok else "🔴 Сбой связи"
        discord_ms = round(self.bot.latency * 1000)

        embed = disnake.Embed(title="💠 Диагностика Mirei", color=BRAND_COLOR)
        embed.add_field(name="📡 Шлюз Discord", value=f"`{discord_ms} мс`", inline=True)
        embed.add_field(
            name="💾 API и база данных",
            value=f"`{backend_ms} мс` ({backend_status})",
            inline=True,
        )
        embed.add_field(name="⚡ Статус", value="В сети", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="server_info",
        description="Показать информацию о сервере",
    )
    async def server_info(self, inter: disnake.ApplicationCommandInteraction):
        guild = inter.guild
        bots = sum(1 for member in guild.members if member.bot)
        total = guild.member_count or len(guild.members)
        humans = max(0, total - bots)

        embed = disnake.Embed(
            title=f"📊 Информация о сервере: {guild.name}",
            color=BRAND_COLOR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Владелец", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="📅 Создан", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
        embed.add_field(
            name="👥 Участники",
            value=f"Всего: **{total}**\nЛюдей: {humans} | Ботов: {bots}",
            inline=True,
        )
        embed.add_field(
            name="💬 Каналы",
            value=f"Текстовых: {len(guild.text_channels)} | Голосовых: {len(guild.voice_channels)}",
            inline=True,
        )
        embed.add_field(name="🎭 Роли", value=f"Всего: **{len(guild.roles)}**", inline=True)
        embed.add_field(
            name="🛡️ Уровень верификации Discord",
            value=str(guild.verification_level).capitalize(),
            inline=True,
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="avatar",
        description="Показать аватар участника",
    )
    async def avatar(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(
            default=None, description="Чей аватар показать"
        ),
    ):
        target = member or inter.author
        avatar_url = target.display_avatar.url
        embed = disnake.Embed(
            title=f"🔍 Аватар: {target.display_name}",
            description=f"[Скачать оригинал]({avatar_url})",
            color=BRAND_COLOR,
        )
        embed.set_image(url=avatar_url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="user_profile",
        description="Показать профиль участника в базе данных",
    )
    @commands.default_member_permissions(administrator=True)
    async def user_profile(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = None,
    ):
        await inter.response.defer(ephemeral=True)
        target = member or inter.author
        user_data = await api.get_user_profile(str(inter.guild_id), str(target.id))

        if not user_data:
            await inter.edit_original_response(
                content=f"API не вернуло профиль участника {target.mention}."
            )
            return

        embed = disnake.Embed(
            title=f"📋 Профиль в БД: {target.display_name}",
            color=BRAND_COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Discord ID", value=f"`{user_data.get('discordId')}`", inline=True)
        embed.add_field(
            name="Верификация",
            value="✅ Подтверждена" if user_data.get("isVerified") else "❌ Не подтверждена",
            inline=True,
        )
        saved_roles = ", ".join(f"<@&{role_id}>" for role_id in user_data.get("roles") or []) or "Нет"
        embed.add_field(name="Сохранённые роли", value=saved_roles[:1024], inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="test_join",
        description="Симулировать вход участника и проверить восстановление ролей",
    )
    @commands.default_member_permissions(administrator=True)
    async def test_join(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = None,
    ):
        await inter.response.defer(ephemeral=True)
        target = member or inter.author
        audit = self.bot.get_cog("Audit")

        if audit is None:
            await inter.edit_original_response(content="Модуль аудита не загружен.")
            return

        await audit.on_member_join(target)
        await inter.edit_original_response(
            content=f"✅ Вход {target.mention} симулирован. Проверь роли и канал журнала."
        )


def setup(bot: commands.Bot):
    bot.add_cog(Utility(bot))