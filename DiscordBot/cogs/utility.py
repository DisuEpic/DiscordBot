import time
import disnake
from disnake.ext import commands
from typing import Optional
from api import api
from views import SettingsDashboardView
from config import (
    GUILD_ONLY, BRAND_COLOR, TACTICAL_GREEN,
    UNIFIED_FOOTER, VERIFY_TIMEOUT_MINUTES
)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="help",
        description="💠 Список возможностей и команд Mirei"
    )
    async def help_cmd(self, inter: disnake.ApplicationCommandInteraction):
        embed = disnake.Embed(
            title="💠 Справочный центр Mirei",
            description=(
                "Привет! Я **Mirei** 🌸 — твой умный ИИ-ассистент и модульная система защиты сервера.\n"
                "Вот что я умею прямо сейчас:"
            ),
            color=BRAND_COLOR
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(
            name="🧠 Живой ИИ-чат",
            value=(
                "• Просто тегни меня или ответь на моё сообщение (`Reply`)\n"
                "• Понимаю картинки (даже внутри Embed), знаю каналы, правила сервера, погоду, курсы и новости\n"
                "• `/ai` — панель выбора нейросети, режима перегрузки, сценария и правил *(Админ)*"
            ),
            inline=False
        )
        embed.add_field(
            name="🛡️ Защита, Верификация и Настройка",
            value=(
                "• `/setup_config` — настройка ролей, каналов, капчи, автокика, ловушки и войсов *(Админ)*\n"
                "• `/settings` — текущая конфигурация и сброс параметров *(Админ)*\n"
                "• `/send_verify_panel` / `/edit_verify_panel` — панель верификации с капчей *(Админ)*\n"
                "• `/set_welcome` — настройка текста приветствия *(Админ)*\n"
                "• `/unverify` — сброс верификации участника *(Модер)*"
            ),
            inline=False
        )
        embed.add_field(
            name="🔨 Модерация",
            value=(
                "• `/timeout`, `/kick`, `/ban`, `/unban` — управление нарушителями\n"
                "• `/clear` — очистка до 100 сообщений\n"
                "• `/lock`, `/unlock`, `/slowmode` — контроль чата"
            ),
            inline=False
        )
        embed.add_field(
            name="🔊 Приватные войсы и 🎭 Роли по кнопкам",
            value=(
                "• Зайди в канал-генератор войсов — создам личную комнату с кнопками управления\n"
                "• `/add_role`, `/delete_role`, `/send_category_panel`, `/send_all_categories`, `/edit_category_panel`\n"
                "• `/give_role`, `/take_role` — ручная выдача ролей"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 Статистика и Утилиты",
            value=(
                "• `/stats setup` | `refresh` | `toggle` | `remove` — счётчики статистики в каналах *(Админ)*\n"
                "• `/server_stats` — подробная живая статистика сервера\n"
                "• `/scan`, `/server_info`, `/avatar`, `/ping`"
            ),
            inline=False
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="setup_config",
        description="Единая настройка каналов, верификации, автокика, ловушки и приватных войсов"
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
        voice_room_template: Optional[str] = commands.Param(default=None, description="Шаблон имени приватной комнаты (например: ╠ 〘🔊〙 {user})"),
        create_voice_hub: bool = commands.Param(default=False, description="Автоматически создать категорию и канал для приватных войсов?"),
        use_captcha: Optional[bool] = commands.Param(default=None, description="Требовать ввод капчи при верификации для новых аккаунтов?"),
        auto_kick_unverified: Optional[bool] = commands.Param(default=None, description="Кикать новичков, если они не прошли верификацию вовремя?"),
        verify_timeout_minutes: Optional[int] = commands.Param(default=None, description="Через сколько минут кикать неверифицированных (1-1440)", ge=1, le=1440),
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        existing = await api.get_guild_config(guild_id) or {}

        sec_existing = existing.get("security") or {}
        wel_existing = existing.get("welcome") or {}
        voi_existing = existing.get("voice") or {}

        target_voice_hub = voice_hub_channel
        if create_voice_hub and not target_voice_hub:
            existing_hub_id = voi_existing.get("generatorChannelId")
            if existing_hub_id and str(existing_hub_id).isdigit():
                ch = inter.guild.get_channel(int(existing_hub_id))
                if isinstance(ch, disnake.VoiceChannel):
                    target_voice_hub = ch

            if not target_voice_hub:
                for v_ch in inter.guild.voice_channels:
                    if "создать комнату" in v_ch.name.lower():
                        target_voice_hub = v_ch
                        break

            if not target_voice_hub:
                try:
                    category = disnake.utils.get(inter.guild.categories, name="── 〘🔊〙 Голосовые 〘🔊〙 ──")
                    if not category:
                        category = await inter.guild.create_category("── 〘🔊〙 Голосовые 〘🔊〙 ──")
                    target_voice_hub = await inter.guild.create_voice_channel("╔ 〘➕〙 Создать комнату", category=category)
                except disnake.Forbidden:
                    await inter.edit_original_response(content="⚠️ У бота недостаточно прав для автоматического создания каналов.")
                    return

        ok = True

        if log_channel is not None:
            ok = ok and await api.update_general_config(guild_id, str(log_channel.id))

        if any(x is not None for x in (verification_role, trap_channel, use_captcha, auto_kick_unverified, verify_timeout_minutes)):
            sec_payload = {
                "verificationRoleId": str(verification_role.id) if verification_role else sec_existing.get("verificationRoleId"),
                "trapChannelId": str(trap_channel.id) if trap_channel else sec_existing.get("trapChannelId"),
                "useCaptcha": use_captcha if use_captcha is not None else sec_existing.get("useCaptcha", True),
                "autoKickUnverified": auto_kick_unverified if auto_kick_unverified is not None else sec_existing.get("autoKickUnverified", False),
                "verifyTimeoutMinutes": verify_timeout_minutes if verify_timeout_minutes is not None else sec_existing.get("verifyTimeoutMinutes", VERIFY_TIMEOUT_MINUTES),
            }
            ok = ok and await api.update_security_config(guild_id, sec_payload)

        if welcome_channel is not None:
            wel_payload = {
                "channelId": str(welcome_channel.id),
                "title": wel_existing.get("title"),
                "description": wel_existing.get("description"),
            }
            ok = ok and await api.update_welcome_config(guild_id, wel_payload)

        if target_voice_hub is not None or voice_room_template is not None:
            voi_payload = {
                "generatorChannelId": str(target_voice_hub.id) if target_voice_hub else voi_existing.get("generatorChannelId"),
                "roomTemplate": voice_room_template.strip() if voice_room_template else voi_existing.get("roomTemplate"),
            }
            ok = ok and await api.update_voice_config(guild_id, voi_payload)

        if not ok:
            await inter.edit_original_response(content="❌ Ошибка при сохранении конфигурации в БД.")
            return

        cfg = await api.get_guild_config(guild_id) or {}
        sec = cfg.get("security") or {}
        wel = cfg.get("welcome") or {}
        voi = cfg.get("voice") or {}

        v_role_text = f"<@&{sec['verificationRoleId']}>" if sec.get("verificationRoleId") else "Не задана"
        captcha_text = "Вкл" if sec.get("useCaptcha", True) else "Выкл"
        autokick_text = f"Вкл ({sec.get('verifyTimeoutMinutes', VERIFY_TIMEOUT_MINUTES)} мин.)" if sec.get("autoKickUnverified") else "Выкл"
        voice_text = f"<#{voi['generatorChannelId']}> (Шаблон: `{voi.get('roomTemplate') or 'Авто'}`)" if voi.get("generatorChannelId") else "Не заданы"

        embed = disnake.Embed(title="⚙️ Конфигурация сервера успешно сохранена!", color=TACTICAL_GREEN)
        embed.add_field(
            name="🛡️ Верификация",
            value=f"Роль: {v_role_text}\nКапча: `{captcha_text}` | Автокик: `{autokick_text}`",
            inline=False
        )
        embed.add_field(
            name="👋 Канал приветствий",
            value=f"<#{wel['channelId']}>" if wel.get("channelId") else "Не задан",
            inline=False
        )
        embed.add_field(
            name="📜 Канал аудита (логов)",
            value=f"<#{cfg['logChannelId']}>" if cfg.get("logChannelId") else "Не задан",
            inline=False
        )
        embed.add_field(name="🔊 Приватные войсы", value=voice_text, inline=False)
        embed.add_field(
            name="🤫 Канал-ловушка (Тишина)",
            value=f"<#{sec['trapChannelId']}>" if sec.get("trapChannelId") else "Не задан",
            inline=False
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="settings", description="Посмотреть текущие настройки Mirei и управлять ими")
    @commands.default_member_permissions(administrator=True)
    async def settings(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)

        cfg = await api.get_guild_config(guild_id) or {}
        sec = cfg.get("security") or {}
        wel = cfg.get("welcome") or {}
        voi = cfg.get("voice") or {}
        ai = cfg.get("ai") or {}
        stats = cfg.get("stats") or {}

        all_roles = await api.get_roles(guild_id)
        guild_roles = [r for r in all_roles if str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))]

        v_role = f"<@&{sec['verificationRoleId']}>" if sec.get("verificationRoleId") else "🔴 Не настроена"
        w_chan = f"<#{wel['channelId']}>" if wel.get("channelId") else "⚪ Отключен"
        l_chan = f"<#{cfg['logChannelId']}>" if cfg.get("logChannelId") else "⚪ Отключен"
        t_chan = f"<#{sec['trapChannelId']}> (Кик за сообщение)" if sec.get("trapChannelId") else "⚪ Отключен"

        v_tpl = voi.get("roomTemplate") or "Авто (по стилю канала)"
        v_hub = f"<#{voi['generatorChannelId']}> (Шаблон: `{v_tpl}`)" if voi.get("generatorChannelId") else "⚪ Отключен"

        autokick_str = (
            f"🟢 Включен (`{sec.get('verifyTimeoutMinutes', VERIFY_TIMEOUT_MINUTES)} мин.`)"
            if sec.get("autoKickUnverified") else "⚪ Отключен"
        )
        captcha_str = "🛡️ Включена" if sec.get("useCaptcha", True) else "⚡ В 1 клик"
        ai_chance = int(ai.get("autoReplyChance") or 0)
        ai_str = (
            f"🟢 Вкл | Модель: `{ai.get('provider', 'auto')}` | Авто-чат: `{ai_chance}%`"
            if ai.get("enabled", True) else "🔴 Отключен"
        )
        stats_str = (
            f"🟢 Включена (Стиль: `{(stats.get('style') or 'en').upper()}`)"
            if stats.get("enabled") else "⚪ Отключена (`/stats setup`)"
        )

        categories_set = {r.get("category") or "Общие" for r in guild_roles}
        roles_info = f"Всего: **{len(guild_roles)}** шт. в категориях: {', '.join(f'`{c}`' for c in categories_set)}" if guild_roles else "⚪ Роли не добавлены"

        embed = disnake.Embed(
            title="💠 Центр управления Mirei",
            description=f"Текущая конфигурация сервера **{inter.guild.name}**:",
            color=BRAND_COLOR
        )
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)

        embed.add_field(name="🛡️ Роль верификации", value=f"{v_role} ({captcha_str})", inline=False)
        embed.add_field(name="⏱️ Автокик новичков", value=autokick_str, inline=False)
        embed.add_field(name="👋 Канал приветствий", value=w_chan, inline=False)
        embed.add_field(name="📜 Канал аудита (логов)", value=l_chan, inline=False)
        embed.add_field(name="🔊 Создание приватных войсов", value=v_hub, inline=False)
        embed.add_field(name="🤫 Канал-ловушка (Тишина)", value=t_chan, inline=False)
        embed.add_field(name="📊 Статистика в каналах", value=stats_str, inline=False)
        embed.add_field(name="🧠 Модуль ИИ", value=ai_str, inline=False)
        embed.add_field(name="🎭 Роли для выбора (в базе)", value=roles_info, inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = SettingsDashboardView(author_id=inter.author.id)
        await inter.edit_original_response(embed=embed, view=view)

    @commands.slash_command(contexts=GUILD_ONLY, name="scan", description="🔍 Информация об участнике")
    async def scan(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: Optional[disnake.Member] = commands.Param(default=None, description="Кого проверить")
    ):
        target = member or inter.author
        await inter.response.defer()

        age_days = (disnake.utils.utcnow() - target.created_at).days
        threat_level = "👑 Администратор" if target.guild_permissions.administrator else "🟢 Участник"
        top_role = target.top_role.mention if not target.top_role.is_default() else "Нет"

        embed = disnake.Embed(title=f"🔍 Профиль участника: {target.display_name}", color=BRAND_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`", inline=True)
        embed.add_field(name="Статус", value=threat_level, inline=True)
        embed.add_field(name="Высшая роль", value=top_role, inline=True)
        embed.add_field(name="На сервере с", value=target.joined_at.strftime("%d.%m.%Y") if target.joined_at else "N/A", inline=True)
        embed.add_field(name="Аккаунт создан", value=f"{target.created_at.strftime('%d.%m.%Y')} ({age_days} дн.)", inline=True)
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

        embed = disnake.Embed(title="💠 Диагностика систем Mirei", color=BRAND_COLOR)
        embed.add_field(name="📡 Шлюз Discord", value=f"`{discord_ping} ms`", inline=True)
        embed.add_field(name="💾 База данных C#", value=f"`{backend_time} ms` ({backend_status})", inline=True)
        embed.add_field(name="⚡ Статус", value="`В сети`", inline=True)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @commands.slash_command(contexts=GUILD_ONLY, name="server_info", description="Информация о сервере")
    async def server_info(self, inter: disnake.ApplicationCommandInteraction):
        guild = inter.guild
        # Однопроходный подсчёт без создания промежуточных списков в памяти
        bots = sum(1 for m in guild.members if m.bot)
        total = guild.member_count or len(guild.members)
        humans = max(0, total - bots)
        created_at = guild.created_at.strftime("%d.%m.%Y")

        embed = disnake.Embed(title=f"📊 Информация о сервере: {guild.name}", color=BRAND_COLOR)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Владелец", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="📅 Создан", value=created_at, inline=True)
        embed.add_field(name="👥 Участники", value=f"Всего: **{total}**\n(Людей: {humans} | Ботов: {bots})", inline=True)
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
            color=BRAND_COLOR
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

        embed = disnake.Embed(title=f"📋 Профиль в БД: {target.display_name}", color=BRAND_COLOR)
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