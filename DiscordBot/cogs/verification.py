import time
import random
import asyncio
import disnake
from disnake.ext import commands, tasks
from typing import Optional, List
from api import api
from utils import (
    send_log, send_welcome_card, check_moderation_target,
    DEFAULT_WELCOME_TITLE, DEFAULT_WELCOME_DESC
)
from views import VerifyView
from cogs.audit import is_safe_to_restore_role
from config import (
    GUILD_ONLY, VERIFY_TIMEOUT_MINUTES, VERIFY_WINDOW_HOURS,
    CAPTCHA_ACCOUNT_DAYS, TACTICAL_GREEN, COMBAT_RED, UNIFIED_FOOTER, log
)


class CaptchaModal(disnake.ui.Modal):
    """Интерактивная капча во всплывающем окне (показывается только новым аккаунтам)."""
    def __init__(self, cog: "Verification"):
        self.cog = cog
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        self.expected_code = "".join(random.choices(alphabet, k=5))

        components = [
            disnake.ui.TextInput(
                label=f"Введите проверочный код: {self.expected_code}",
                placeholder=f"Напишите сюда: {self.expected_code}",
                custom_id="captcha_input",
                style=disnake.TextInputStyle.short,
                min_length=5,
                max_length=5,
                required=True,
            )
        ]
        super().__init__(title="🛡️ Защита от ботов (Aigis Captcha)", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        user_input = inter.text_values.get("captcha_input", "").strip().upper()
        if user_input != self.expected_code:
            await inter.response.send_message(
                f"❌ Неверный код (`{user_input}` ≠ `{self.expected_code}`). Нажмите на кнопку верификации и попробуйте еще раз!",
                ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        await self.cog._complete_verification(inter, respond_ephemeral=True, passed_captcha=True)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = disnake.utils.utcnow()
        self.check_unverified_members.start()

    def cog_unload(self):
        self.check_unverified_members.cancel()

    async def _complete_verification(
        self,
        inter: disnake.Interaction,
        respond_ephemeral: bool = False,
        passed_captcha: bool = False
    ):
        guild_id = str(inter.guild_id)
        user_id = str(inter.author.id)

        guild_config = await api.get_guild_config(guild_id)
        sec_cfg = (guild_config or {}).get("security") or {}
        verify_role_id = sec_cfg.get("verificationRoleId")

        if not verify_role_id or not str(verify_role_id).isdigit():
            await inter.followup.send("❌ Роль верификации еще не настроена администрацией.", ephemeral=True)
            return

        verify_role = inter.guild.get_role(int(verify_role_id))
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
            if respond_ephemeral:
                await inter.followup.send("✅ Вы уже верифицированы на сервере!", ephemeral=True)
            return

        success = await api.verify_user(guild_id, user_id)
        if not success:
            await inter.followup.send("⚠️ Сервер базы данных временно недоступен, попробуйте через минуту.", ephemeral=True)
            return

        try:
            await inter.author.add_roles(*roles_to_give, reason="Верификация и восстановление ролей из БД")
            roles_mentions = ", ".join(r.mention for r in roles_to_give)

            if respond_ephemeral:
                await inter.followup.send("✅ Проверка пройдена! Доступ к серверу открыт.", ephemeral=True)

            if was_already_verified:
                return

            extra_restored = [r for r in roles_to_give if r != verify_role]
            await send_welcome_card(inter.author, guild_config or {}, extra_roles=extra_restored)

            captcha_note = "\n**Проверка:** 🛡️ Капча пройдена (новый аккаунт)" if passed_captcha else ""
            log_embed = disnake.Embed(
                title="✅ Участник верифицирован",
                description=(
                    f"**Участник:** {inter.author.mention} (`{inter.author.id}`)\n"
                    f"**Выданы роли:** {roles_mentions}"
                    f"{captcha_note}"
                ),
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_thumbnail(url=inter.author.display_avatar.url)
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, log_embed)

        except disnake.Forbidden:
            await inter.followup.send("⚠️ Ошибка прав: роль бота должна стоять выше выдаваемых ролей.", ephemeral=True)

    @commands.Cog.listener("on_button_click")
    async def on_verify_button(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if cid not in ("persistent_verify_button", "persistent_verify_captcha"):
            return

        guild_config = await api.get_guild_config(str(inter.guild_id))
        verify_role_id = ((guild_config or {}).get("security") or {}).get("verificationRoleId")
        if verify_role_id and str(verify_role_id).isdigit():
            v_role = inter.guild.get_role(int(verify_role_id))
            if v_role and v_role in inter.author.roles:
                await inter.response.send_message("✅ Вы уже прошли верификацию!", ephemeral=True)
                return

        account_age_days = (disnake.utils.utcnow() - inter.author.created_at).days
        is_new_account = account_age_days < CAPTCHA_ACCOUNT_DAYS

        # Капчу показываем ТОЛЬКО новым аккаунтам (младше CAPTCHA_ACCOUNT_DAYS дней)
        if cid == "persistent_verify_captcha" and is_new_account:
            await inter.response.send_modal(CaptchaModal(self))
        else:
            await inter.response.defer()
            await self._complete_verification(inter, respond_ephemeral=False, passed_captcha=False)

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
        cfg = await api.get_guild_config(guild_id) or {}
        wel = dict(cfg.get("welcome") or {})

        if reset_to_default:
            wel["title"] = None
            wel["description"] = None
            if await api.update_welcome_config(guild_id, wel):
                await inter.edit_original_response(content="♻️ Приветствие в базе данных сброшено к стандартному тексту.")
            else:
                await inter.edit_original_response(content="❌ Ошибка сохранения в БД.")
            return

        if not title and not description:
            await inter.edit_original_response(content="⚠️ Укажите новый заголовок или описание (или выберите сброс).")
            return

        if title:
            wel["title"] = title
        if description:
            wel["description"] = description

        if not await api.update_welcome_config(guild_id, wel):
            await inter.edit_original_response(content="❌ Не удалось сохранить шаблон приветствия в базу данных.")
            return

        sample_title = (wel.get("title") or DEFAULT_WELCOME_TITLE).replace("{user}", inter.author.display_name).replace("{server}", inter.guild.name)
        sample_desc = (wel.get("description") or DEFAULT_WELCOME_DESC).replace("{user}", inter.author.mention).replace("{server}", inter.guild.name)

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
            sec = (cfg or {}).get("security") or {}
            if not sec.get("autoKickUnverified", False):
                continue

            verify_role_id = sec.get("verificationRoleId")
            if not verify_role_id or not str(verify_role_id).isdigit():
                continue

            verify_role = guild.get_role(int(verify_role_id))
            if not verify_role:
                continue

            timeout_mins = sec.get("verifyTimeoutMinutes") or VERIFY_TIMEOUT_MINUTES

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
                if minutes_waiting >= timeout_mins:
                    try:
                        try:
                            dm_embed = disnake.Embed(
                                title="⏳ Превышен лимит ожидания верификации",
                                description=(
                                    f"Здравствуйте, **{member.display_name}**.\n\n"
                                    f"Время на прохождение верификации на сервере **{guild.name}** ({timeout_mins} мин.) истекло.\n"
                                    f"Вы были исключены с сервера. Вы можете зайти снова и подтвердить профиль вовремя."
                                ),
                                color=COMBAT_RED
                            )
                            dm_embed.set_footer(text=UNIFIED_FOOTER)
                            await member.send(embed=dm_embed)
                        except disnake.Forbidden:
                            pass

                        await member.kick(reason=f"Не прошел верификацию за {timeout_mins} минут")

                        log_embed = disnake.Embed(
                            title="⏳ Исключение (Таймаут верификации)",
                            description=(
                                f"**Участник:** {member.mention} (`{member.id}`)\n"
                                f"**Причина:** Не прошел верификацию за `{timeout_mins}` мин."
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

    @commands.slash_command(contexts=GUILD_ONLY, name="send_verify_panel", description="Отправить панель верификации (с капчей для новых аккаунтов или в 1 клик)")
    @commands.default_member_permissions(administrator=True)
    async def send_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        title: str = "🛡️ Верификация на сервере",
        description: Optional[str] = None,
        button_label: str = "Пройти верификацию",
        button_emoji: str = "✅",
        use_captcha: Optional[bool] = commands.Param(default=None, description="Включить капчу для новых аккаунтов? (по умолчанию из настроек)")
    ):
        await inter.response.defer(ephemeral=True)
        if use_captcha is None:
            cfg = await api.get_guild_config(str(inter.guild_id)) or {}
            final_captcha = (cfg.get("security") or {}).get("useCaptcha", True)
        else:
            final_captcha = use_captcha

        final_desc = description or (
            f"Добро пожаловать на сервер **{inter.guild.name}**!\n"
            f"Нажмите на кнопку ниже, чтобы подтвердить профиль и получить доступ к каналам."
        )
        embed = disnake.Embed(title=title, description=final_desc, color=TACTICAL_GREEN)
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = VerifyView(button_label=button_label, button_emoji=button_emoji, use_captcha=final_captcha)
        await inter.channel.send(embed=embed, view=view)
        mode_str = f"с капчей для аккаунтов < {CAPTCHA_ACCOUNT_DAYS} дн." if final_captcha else "в 1 клик для всех"
        await inter.edit_original_response(content=f"✅ Панель верификации ({mode_str}) успешно отправлена в канал!")

    @commands.slash_command(contexts=GUILD_ONLY, name="edit_verify_panel", description="Отредактировать панель верификации")
    @commands.default_member_permissions(administrator=True)
    async def edit_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(description="ID сообщения панели в этом канале"),
        title: Optional[str] = commands.Param(default=None, description="Новый заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Новый текст описания"),
        button_label: Optional[str] = commands.Param(default=None, description="Новая надпись на кнопке"),
        button_emoji: Optional[str] = commands.Param(default=None, description="Новый эмодзи на кнопке"),
        use_captcha: Optional[bool] = commands.Param(default=None, description="Включить капчу для новых аккаунтов?")
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

        if use_captcha is None:
            old_cid = getattr(old_btn, "custom_id", "") if old_btn else ""
            final_captcha = old_cid == "persistent_verify_captcha"
        else:
            final_captcha = use_captcha

        view = VerifyView(button_label=new_label, button_emoji=new_emoji, use_captcha=final_captcha)
        await msg.edit(content=None, embed=new_embed, view=view)
        await inter.edit_original_response(content="✅ Панель верификации успешно обновлена!")


def setup(bot: commands.Bot):
    bot.add_cog(Verification(bot))