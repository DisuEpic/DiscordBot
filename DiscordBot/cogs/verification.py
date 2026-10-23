import os
import json
import asyncio
import disnake
from disnake.ext import commands, tasks
from typing import Optional, List
from api import api
from utils import send_log
from views import VerifyView
from config import (
    GUILD_ONLY, VERIFY_TIMEOUT_MINUTES, VERIFY_WINDOW_HOURS,
    TACTICAL_GREEN, COMBAT_RED, UNIFIED_FOOTER, log
)

WELCOME_CONFIG_FILE = "welcome_config.json"

def load_welcome_config() -> dict:
    if os.path.exists(WELCOME_CONFIG_FILE):
        try:
            with open(WELCOME_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_welcome_config(cfg: dict):
    try:
        with open(WELCOME_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("Не удалось сохранить welcome_config.json: %s", e)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = disnake.utils.utcnow()
        self.check_unverified_members.start()

    def cog_unload(self):
        self.check_unverified_members.cancel()

    @commands.Cog.listener("on_button_click")
    async def on_verify_button(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "persistent_verify_button":
            return

        # Тихо подтверждаем клик без редактирования сообщения панели
        await inter.response.defer()
        guild_id = str(inter.guild_id)
        user_id = str(inter.author.id)

        guild_config = await api.get_guild_config(guild_id)
        if not guild_config or not guild_config.get("verificationRoleId"):
            return

        verify_role = inter.guild.get_role(int(guild_config["verificationRoleId"]))
        if not verify_role:
            return

        profile = await api.get_user_profile(guild_id, user_id)
        saved_role_ids = set(str(r) for r in (profile.get("roles") or [])) if profile else set()

        roles_to_give: List[disnake.Role] = []
        if verify_role not in inter.author.roles:
            roles_to_give.append(verify_role)

        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        for r_id in saved_role_ids:
            if not r_id.isdigit():
                continue
            r = inter.guild.get_role(int(r_id))
            if (
                r
                and r not in inter.author.roles
                and r not in roles_to_give
                and not r.is_default()
                and not r.managed
                and not r.permissions.administrator
                and (bot_top_role is None or r < bot_top_role)
            ):
                roles_to_give.append(r)

        was_already_verified = verify_role in inter.author.roles
        if was_already_verified and not roles_to_give:
            return

        success = await api.verify_user(guild_id, user_id)
        if not success:
            return

        try:
            await inter.author.add_roles(*roles_to_give, reason="Верификация и восстановление ролей из БД")
            roles_mentions = ", ".join(r.mention for r in roles_to_give)

            if was_already_verified:
                return

            if guild_config.get("welcomeChannelId"):
                welcome_channel = inter.guild.get_channel(int(guild_config["welcomeChannelId"]))
                if welcome_channel and isinstance(welcome_channel, disnake.TextChannel):
                    custom_cfg = load_welcome_config().get(guild_id, {})
                    raw_title = custom_cfg.get("title") or "🛡️ Допуск подтвержден: {server}"
                    raw_desc = custom_cfg.get("description") or (
                        "Субъект {user} успешно верифицирован в защитном реестре.\n"
                        "Протоколы безопасности активированы. Добро пожаловать в периметр!"
                    )

                    final_title = raw_title.replace("{user}", inter.author.display_name).replace("{server}", inter.guild.name)
                    final_desc = raw_desc.replace("{user}", inter.author.mention).replace("{server}", inter.guild.name)

                    welcome_embed = disnake.Embed(
                        title=final_title,
                        description=final_desc,
                        color=TACTICAL_GREEN
                    )
                    if len(roles_to_give) > 1:
                        welcome_embed.add_field(name="♻️ Синхронизированы роли:", value=roles_mentions[:1024], inline=False)
                    welcome_embed.set_thumbnail(url=inter.author.display_avatar.url)
                    welcome_embed.set_footer(text=UNIFIED_FOOTER)
                    try:
                        await welcome_channel.send(embed=welcome_embed)
                    except disnake.Forbidden:
                        pass

            log_embed = disnake.Embed(
                title="🛡️ Субъект верифицирован",
                description=f"Субъект {inter.author.mention} (`{inter.author.id}`) успешно прошел проверку личности.\n**Выданы роли:** {roles_mentions}",
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)

        except disnake.Forbidden:
            pass

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="set_welcome",
        description="Настроить текст карточки приветствия в канале"
    )
    @commands.default_member_permissions(administrator=True)
    async def set_welcome(
        self,
        inter: disnake.ApplicationCommandInteraction,
        title: Optional[str] = commands.Param(default=None, description="Заголовок (доступно: {user}, {server})"),
        description: Optional[str] = commands.Param(default=None, description="Текст описания (доступно: {user}, {server})"),
        reset_to_default: bool = commands.Param(default=False, description="Сбросить к тексту по умолчанию?")
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        all_cfg = load_welcome_config()

        if reset_to_default:
            all_cfg.pop(guild_id, None)
            save_welcome_config(all_cfg)
            await inter.edit_original_response(content="♻️ Приветствие сброшено к стандартному тексту.")
            return

        if not title and not description:
            await inter.edit_original_response(content="⚠️ Укажите новый заголовок или описание (или выберите сброс).")
            return

        guild_welcome = all_cfg.setdefault(guild_id, {})
        if title:
            guild_welcome["title"] = title
        if description:
            guild_welcome["description"] = description

        save_welcome_config(all_cfg)

        sample_title = (guild_welcome.get("title") or "🛡️ Допуск подтвержден: {server}").replace("{user}", inter.author.display_name).replace("{server}", inter.guild.name)
        sample_desc = (guild_welcome.get("description") or (
            "Субъект {user} успешно верифицирован в защитном реестре.\n"
            "Протоколы безопасности активированы. Добро пожаловать в периметр!"
        )).replace("{user}", inter.author.mention).replace("{server}", inter.guild.name)

        preview_embed = disnake.Embed(title=f"Предпросмотр: {sample_title}", description=sample_desc, color=TACTICAL_GREEN)
        preview_embed.set_thumbnail(url=inter.author.display_avatar.url)
        preview_embed.set_footer(text=UNIFIED_FOOTER)

        await inter.edit_original_response(
            content="✅ Шаблон приветствия успешно сохранен! Предпросмотр:",
            embed=preview_embed
        )

    @tasks.loop(minutes=1.0)
    async def check_unverified_members(self):
        now = disnake.utils.utcnow()
        for guild in self.bot.guilds:
            cfg = await api.get_guild_config(str(guild.id))
            if not cfg or not cfg.get("verificationRoleId"):
                continue

            verify_role = guild.get_role(int(cfg["verificationRoleId"]))
            if not verify_role:
                continue

            for member in list(guild.members):
                if member.bot or member.guild_permissions.administrator:
                    continue
                if member.joined_at is None or verify_role in member.roles:
                    continue

                minutes_on_server = (now - member.joined_at).total_seconds() / 60
                if minutes_on_server > VERIFY_WINDOW_HOURS * 60:
                    continue

                waiting_since = max(member.joined_at, self.started_at)
                minutes_waiting = (now - waiting_since).total_seconds() / 60
                if minutes_waiting >= VERIFY_TIMEOUT_MINUTES:
                    try:
                        try:
                            dm_embed = disnake.Embed(
                                title="⏳ Превышен лимит ожидания верификации",
                                description=(
                                    f"Здравствуйте, **{member.display_name}**.\n\n"
                                    f"Время на прохождение верификации на сервере **{guild.name}** ({VERIFY_TIMEOUT_MINUTES} мин.) истекло.\n"
                                    f"Вы были исключены с сервера. Вы можете зайти снова и подтвердить профиль вовремя."
                                ),
                                color=COMBAT_RED
                            )
                            dm_embed.set_footer(text=UNIFIED_FOOTER)
                            await member.send(embed=dm_embed)
                        except disnake.Forbidden:
                            pass

                        await member.kick(reason=f"Не прошел верификацию за {VERIFY_TIMEOUT_MINUTES} минут")

                        log_embed = disnake.Embed(
                            title="⏳ Автоматическое исключение (Таймаут верификации)",
                            description=f"Субъект {member.mention} (`{member.id}`) не прошел верификацию за `{VERIFY_TIMEOUT_MINUTES}` мин. и был исключен.",
                            color=COMBAT_RED,
                            timestamp=disnake.utils.utcnow()
                        )
                        log_embed.set_footer(text=UNIFIED_FOOTER)
                        await send_log(guild, log_embed)
                        await asyncio.sleep(1.0)
                    except disnake.Forbidden:
                        pass
                    except disnake.HTTPException:
                        log.exception("Не удалось кикнуть неверифицированного участника %s", member.id)

    @check_unverified_members.before_loop
    async def before_check_unverified(self):
        await self.bot.wait_until_ready()

    @commands.slash_command(contexts=GUILD_ONLY, name="send_verify_panel", description="Отправить панель верификации")
    @commands.default_member_permissions(administrator=True)
    async def send_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        title: str = "🛡️ Протокол допуска: Система безопасности Aigis",
        description: Optional[str] = None,
        button_label: str = "Инициализировать допуск",
        button_emoji: str = "🤖"
    ):
        final_desc = description or (
            f"Приветствую. Я автономный модуль защиты сервера **{inter.guild.name}**. "
            f"Для подтверждения личности и деактивации защитных барьеров инициализируйте допуск."
        )
        embed = disnake.Embed(title=title, description=final_desc, color=TACTICAL_GREEN)
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = VerifyView(button_label=button_label, button_emoji=button_emoji)
        await inter.channel.send(embed=embed, view=view)
        await inter.response.send_message("✅ Панель верификации успешно отправлена в канал!", ephemeral=True)

    @commands.slash_command(contexts=GUILD_ONLY, name="edit_verify_panel", description="Отредактировать панель верификации")
    @commands.default_member_permissions(administrator=True)
    async def edit_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(description="ID сообщения панели в этом канале"),
        title: Optional[str] = commands.Param(default=None, description="Новый заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Новый текст описания"),
        button_label: Optional[str] = commands.Param(default=None, description="Новая надпись на кнопке"),
        button_emoji: Optional[str] = commands.Param(default=None, description="Новый эмодзи на кнопке")
    ):
        await inter.response.defer(ephemeral=True)
        try:
            msg = await inter.channel.fetch_message(int(message_id))
        except Exception:
            await inter.edit_original_response(content="❌ Сообщение с таким ID не найдено в этом канале.")
            return

        if msg.author.id != self.bot.user.id or not msg.embeds:
            await inter.edit_original_response(content="❌ Невозможно отредактировать данное сообщение.")
            return

        old_embed = msg.embeds[0]
        new_embed = disnake.Embed(
            title=title or old_embed.title,
            description=description or old_embed.description,
            color=old_embed.color
        )
        if old_embed.thumbnail:
            new_embed.set_thumbnail(url=old_embed.thumbnail.url)
        new_embed.set_footer(text=UNIFIED_FOOTER)

        old_btn = msg.components[0].children[0] if msg.components and msg.components[0].children else None
        new_label = button_label or (old_btn.label if old_btn and old_btn.label else "Инициализировать допуск")
        new_emoji = button_emoji or (str(old_btn.emoji) if old_btn and old_btn.emoji else "🤖")
        view = VerifyView(button_label=new_label, button_emoji=new_emoji)
        await msg.edit(content=None, embed=new_embed, view=view)
        await inter.edit_original_response(content="✅ Панель верификации успешно обновлена!")

def setup(bot: commands.Bot):
    bot.add_cog(Verification(bot))