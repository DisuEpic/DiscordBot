import time
import asyncio
import disnake
from disnake.ext import commands, tasks
from typing import Optional, List
from api import api
from utils import send_log, check_moderation_target
from views import VerifyView
from cogs.audit import is_safe_to_restore_role
from config import (
    GUILD_ONLY, VERIFY_TIMEOUT_MINUTES, VERIFY_WINDOW_HOURS,
    TACTICAL_GREEN, COMBAT_RED, UNIFIED_FOOTER, log
)

DEFAULT_WELCOME_TITLE = "🛡️ Верификация пройдена: {server}"
DEFAULT_WELCOME_DESC = (
    "Участник {user} успешно прошел верификацию.\n"
    "Добро пожаловать на сервер!"
)

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

        await inter.response.defer()
        guild_id = str(inter.guild_id)
        user_id = str(inter.author.id)

        guild_config = await api.get_guild_config(guild_id)
        if not guild_config or not guild_config.get("verificationRoleId"):
            await inter.followup.send("❌ Роль верификации еще не настроена администрацией.", ephemeral=True)
            return

        verify_role = inter.guild.get_role(int(guild_config["verificationRoleId"]))
        if not verify_role:
            await inter.followup.send("⚠️ Роль верификации не найдена на сервере.", ephemeral=True)
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
                and is_safe_to_restore_role(r, bot_top_role)
            ):
                roles_to_give.append(r)

        was_already_verified = verify_role in inter.author.roles
        if was_already_verified and not roles_to_give:
            return

        success = await api.verify_user(guild_id, user_id)
        if not success:
            await inter.followup.send("⚠️ Сервер базы данных временно недоступен, попробуйте через минуту.", ephemeral=True)
            return

        try:
            await inter.author.add_roles(*roles_to_give, reason="Верификация и восстановление ролей из БД")
            roles_mentions = ", ".join(r.mention for r in roles_to_give)

            if was_already_verified:
                return

            if guild_config.get("welcomeChannelId"):
                welcome_channel = inter.guild.get_channel(int(guild_config["welcomeChannelId"]))
                if welcome_channel and isinstance(welcome_channel, disnake.TextChannel):
                    raw_title = guild_config.get("welcomeTitle") or DEFAULT_WELCOME_TITLE
                    raw_desc = guild_config.get("welcomeDescription") or DEFAULT_WELCOME_DESC

                    final_title = raw_title.replace("{user}", inter.author.display_name).replace("{server}", inter.guild.name)
                    final_desc = raw_desc.replace("{user}", inter.author.mention).replace("{server}", inter.guild.name)

                    welcome_embed = disnake.Embed(
                        title=final_title,
                        description=final_desc,
                        color=TACTICAL_GREEN
                    )
                    if len(roles_to_give) > 1:
                        welcome_embed.add_field(name="♻️ Восстановлены роли:", value=roles_mentions[:1024], inline=False)
                    welcome_embed.set_thumbnail(url=inter.author.display_avatar.url)
                    welcome_embed.set_footer(text=UNIFIED_FOOTER)
                    try:
                        await welcome_channel.send(embed=welcome_embed)
                    except disnake.Forbidden:
                        pass

            log_embed = disnake.Embed(
                title="✅ Участник верифицирован",
                description=(
                    f"**Участник:** {inter.author.mention} (`{inter.author.id}`)\n"
                    f"**Выданы роли:** {roles_mentions}"
                ),
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_thumbnail(url=inter.author.display_avatar.url)
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)

        except disnake.Forbidden:
            await inter.followup.send("⚠️ Ошибка прав: роль бота должна стоять выше выдаваемых ролей.", ephemeral=True)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="unverify",
        description="Снять верификацию с участника и очистить его сохраненные роли в БД"
    )
    @commands.default_member_permissions(moderate_members=True)
    async def unverify_member(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="У кого снять верификацию"),
        reason: str = commands.Param(default="Снятие верификации модератором", description="Причина")
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error_msg)
            return

        guild_id = str(inter.guild_id)
        bot_top_role = inter.guild.me.top_role if inter.guild.me else None

        roles_to_remove = [
            r for r in member.roles
            if not r.is_default() and not r.managed and (bot_top_role is None or r < bot_top_role)
        ]

        audit_cog = self.bot.get_cog("Audit")
        if audit_cog and hasattr(audit_cog, "_restoring_members"):
            audit_cog._restoring_members[member.id] = time.time()

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Снятие верификации: {reason} ({inter.author})")
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У бота недостаточно прав для снятия ролей с этого участника.")
            return

        await api.unverify_user(guild_id, str(member.id))

        await inter.edit_original_response(
            content=f"🚫 Верификация участника {member.mention} снята! Удалено ролей: **{len(roles_to_remove)}** шт., профиль в БД очищен."
        )

        log_embed = disnake.Embed(
            title="🚫 Верификация снята (Unverify)",
            description=(
                f"**Участник:** {member.mention} (`{member.id}`)\n"
                f"**Модератор:** {inter.author.mention}\n"
                f"**Причина:** {reason}\n"
                f"**Снято ролей:** `{len(roles_to_remove)}` шт."
            ),
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow()
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, log_embed)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="set_welcome",
        description="Настроить текст карточки приветствия в базе данных"
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
        cfg = await api.get_guild_config(guild_id) or {"guildId": guild_id}
        cfg["guildId"] = guild_id

        if reset_to_default:
            cfg["welcomeTitle"] = None
            cfg["welcomeDescription"] = None
            if await api.save_guild_config(cfg):
                await inter.edit_original_response(content="♻️ Приветствие в базе данных сброшено к стандартному тексту.")
            else:
                await inter.edit_original_response(content="❌ Ошибка сохранения в БД.")
            return

        if not title and not description:
            await inter.edit_original_response(content="⚠️ Укажите новый заголовок или описание (или выберите сброс).")
            return

        if title:
            cfg["welcomeTitle"] = title
        if description:
            cfg["welcomeDescription"] = description

        if not await api.save_guild_config(cfg):
            await inter.edit_original_response(content="❌ Не удалось сохранить шаблон приветствия в базу данных.")
            return

        sample_title = (cfg.get("welcomeTitle") or DEFAULT_WELCOME_TITLE).replace("{user}", inter.author.display_name).replace("{server}", inter.guild.name)
        sample_desc = (cfg.get("welcomeDescription") or DEFAULT_WELCOME_DESC).replace("{user}", inter.author.mention).replace("{server}", inter.guild.name)

        preview_embed = disnake.Embed(title=f"Предпросмотр: {sample_title}", description=sample_desc, color=TACTICAL_GREEN)
        preview_embed.set_thumbnail(url=inter.author.display_avatar.url)
        preview_embed.set_footer(text=UNIFIED_FOOTER)

        await inter.edit_original_response(
            content="✅ Шаблон приветствия успешно сохранен в БД! Предпросмотр:",
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
                            title="⏳ Исключение (Таймаут верификации)",
                            description=(
                                f"**Участник:** {member.mention} (`{member.id}`)\n"
                                f"**Причина:** Не прошел верификацию за `{VERIFY_TIMEOUT_MINUTES}` мин."
                            ),
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
        title: str = "🛡️ Верификация на сервере",
        description: Optional[str] = None,
        button_label: str = "Пройти верификацию",
        button_emoji: str = "✅"
    ):
        final_desc = description or (
            f"Добро пожаловать на сервер **{inter.guild.name}**!\n"
            f"Нажмите на кнопку ниже, чтобы подтвердить профиль и получить доступ к каналам."
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
        new_label = button_label or (old_btn.label if old_btn and old_btn.label else "Пройти верификацию")
        new_emoji = button_emoji or (str(old_btn.emoji) if old_btn and old_btn.emoji else "✅")
        view = VerifyView(button_label=new_label, button_emoji=new_emoji)
        await msg.edit(content=None, embed=new_embed, view=view)
        await inter.edit_original_response(content="✅ Панель верификации успешно обновлена!")

def setup(bot: commands.Bot):
    bot.add_cog(Verification(bot))