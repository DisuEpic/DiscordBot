import asyncio
import random
import time
from typing import List, Optional

import disnake
from disnake.ext import commands, tasks

from api import api
from cogs.audit import is_safe_to_restore_role
from config import (
    GUILD_ONLY, VERIFY_TIMEOUT_MINUTES, VERIFY_WINDOW_HOURS,
    CAPTCHA_ACCOUNT_DAYS, TACTICAL_GREEN, COMBAT_RED, UNIFIED_FOOTER, log,
)
from utils import send_log, send_welcome_card, check_moderation_target
from views import VerifyView


class CaptchaModal(disnake.ui.Modal):
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
        super().__init__(
            title="💠 Защита от ботов (Mirei Captcha)", components=components
        )

    async def callback(self, inter: disnake.ModalInteraction):
        user_input = inter.text_values.get("captcha_input", "").strip().upper()
        if user_input != self.expected_code:
            await inter.response.send_message(
                "❌ Неверный код. Нажмите кнопку верификации и попробуйте ещё раз.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True)
        await self.cog._complete_verification(
            inter, respond_ephemeral=True, passed_captcha=True
        )


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
        passed_captcha: bool = False,
    ):
        guild_id = str(inter.guild_id)
        user_id = str(inter.author.id)

        guild_config = await api.get_guild_config(guild_id)
        security = (guild_config or {}).get("security") or {}
        verify_role_id = security.get("verificationRoleId")

        if not verify_role_id or not str(verify_role_id).isdigit():
            await inter.followup.send(
                "❌ Роль верификации ещё не настроена администрацией.",
                ephemeral=True,
            )
            return

        verify_role = inter.guild.get_role(int(verify_role_id))
        if not verify_role:
            await inter.followup.send(
                "⚠️ Роль верификации не найдена на сервере.", ephemeral=True
            )
            return

        profile = await api.get_user_profile(guild_id, user_id)
        saved_role_ids = {str(role_id) for role_id in (profile or {}).get("roles") or []}
        was_already_verified = verify_role in inter.author.roles
        roles_to_give: List[disnake.Role] = []
        if not was_already_verified:
            roles_to_give.append(verify_role)

        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        for role_id in saved_role_ids:
            if not role_id.isdigit():
                continue

            role = inter.guild.get_role(int(role_id))
            if (
                role
                and role not in inter.author.roles
                and role not in roles_to_give
                and is_safe_to_restore_role(role, bot_top_role)
            ):
                roles_to_give.append(role)

        if was_already_verified and not roles_to_give and profile and profile.get("isVerified"):
            if respond_ephemeral:
                await inter.followup.send(
                    "✅ Вы уже верифицированы на сервере.", ephemeral=True
                )
            return

        try:
            if roles_to_give:
                await inter.author.add_roles(
                    *roles_to_give, reason="Верификация и восстановление ролей из БД"
                )

            if not await api.verify_user(guild_id, user_id):
                await inter.followup.send(
                    "Роли обновлены в Discord. API не подтвердило сохранение. "
                    "Нажмите кнопку верификации повторно.",
                    ephemeral=True,
                )
                return

            if respond_ephemeral:
                await inter.followup.send(
                    "✅ Проверка пройдена! Доступ к серверу открыт.", ephemeral=True
                )

            if was_already_verified:
                return

            extra_restored = [role for role in roles_to_give if role != verify_role]
            await send_welcome_card(
                inter.author, guild_config or {}, extra_roles=extra_restored
            )

            roles_mentions = ", ".join(role.mention for role in roles_to_give)
            captcha_note = (
                "\n**Проверка:** 🛡️ Капча пройдена (новый аккаунт)" if passed_captcha else ""
            )
            embed = disnake.Embed(
                title="✅ Участник верифицирован",
                description=(
                    f"**Участник:** {inter.author.mention} (`{inter.author.id}`)\n"
                    f"**Выданы роли:** {roles_mentions}{captcha_note}"
                ),
                color=TACTICAL_GREEN,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_thumbnail(url=inter.author.display_avatar.url)
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(inter.guild, embed)

        except disnake.HTTPException:
            await inter.followup.send(
                "Discord не подтвердил завершение проверки. "
                "Проверьте роли и повторите попытку.",
                ephemeral=True,
            )

    @commands.Cog.listener("on_button_click")
    async def on_verify_button(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id
        if custom_id not in ("persistent_verify_button", "persistent_verify_captcha"):
            return

        account_age_days = (disnake.utils.utcnow() - inter.author.created_at).days
        if custom_id == "persistent_verify_captcha" and account_age_days < CAPTCHA_ACCOUNT_DAYS:
            await inter.response.send_modal(CaptchaModal(self))
            return

        await inter.response.defer(ephemeral=True)
        await self._complete_verification(inter, respond_ephemeral=True)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="верификация",
        description="Управление верификацией",
    )
    async def verification(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @verification.sub_command(
        name="снять",
        description="Снять верификацию и очистить сохранённые роли в БД",
    )
    @commands.has_guild_permissions(moderate_members=True)
    async def unverify_member(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(
            name="участник", description="У кого снять верификацию"
        ),
        reason: str = commands.Param(
            name="причина",
            default="Снятие верификации модератором",
            description="Причина",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_moderation_target(inter, member):
            await inter.edit_original_response(content=error)
            return

        guild_id = str(inter.guild_id)
        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        roles_to_remove = [
            role
            for role in member.roles
            if not role.is_default()
            and not role.managed
            and (bot_top_role is None or role < bot_top_role)
        ]

        if not await api.unverify_user(guild_id, str(member.id)):
            await inter.edit_original_response(
                content="API не подтвердило сброс профиля. Повтори команду."
            )
            return

        audit_cog = self.bot.get_cog("Audit")
        if audit_cog and hasattr(audit_cog, "_restoring_members"):
            audit_cog._restoring_members[(inter.guild_id, member.id)] = time.time()

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Снятие верификации: {reason} ({inter.author})",
                )
        except disnake.HTTPException:
            await inter.edit_original_response(
                content=(
                    "Профиль очищен в БД. Discord не подтвердил снятие всех ролей. "
                    "Повтори команду."
                )
            )
            return

        await inter.edit_original_response(
            content=(
                f"🚫 Верификация участника {member.mention} снята. "
                f"Удалено ролей: **{len(roles_to_remove)}**. Профиль в БД очищен."
            )
        )

        embed = disnake.Embed(
            title="🚫 Верификация снята",
            description=(
                f"**Участник:** {member.mention} (`{member.id}`)\n"
                f"**Модератор:** {inter.author.mention}\n"
                f"**Причина:** {reason}\n"
                f"**Снято ролей:** `{len(roles_to_remove)}` шт."
            ),
            color=COMBAT_RED,
            timestamp=disnake.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=UNIFIED_FOOTER)
        await send_log(inter.guild, embed)

    @tasks.loop(minutes=1.0)
    async def check_unverified_members(self):
        now = disnake.utils.utcnow()
        window_minutes = VERIFY_WINDOW_HOURS * 60

        for guild in list(self.bot.guilds):
            cfg = await api.get_guild_config(str(guild.id))
            security = (cfg or {}).get("security") or {}
            if not security.get("autoKickUnverified", False):
                await asyncio.sleep(0)
                continue

            verify_role_id = security.get("verificationRoleId")
            if not verify_role_id or not str(verify_role_id).isdigit():
                await asyncio.sleep(0)
                continue

            verify_role = guild.get_role(int(verify_role_id))
            if not verify_role:
                await asyncio.sleep(0)
                continue

            timeout_minutes = security.get("verifyTimeoutMinutes") or VERIFY_TIMEOUT_MINUTES
            for member in list(guild.members):
                if member.bot or member.guild_permissions.administrator:
                    continue
                if member.joined_at is None or verify_role in member.roles:
                    continue

                minutes_on_server = (now - member.joined_at).total_seconds() / 60
                if minutes_on_server > window_minutes:
                    continue

                waiting_since = max(member.joined_at, self.started_at)
                minutes_waiting = (now - waiting_since).total_seconds() / 60
                if minutes_waiting < timeout_minutes:
                    continue

                try:
                    try:
                        dm_embed = disnake.Embed(
                            title="⏳ Превышен лимит ожидания верификации",
                            description=(
                                f"Здравствуйте, **{member.display_name}**.\n\n"
                                f"Время на верификацию на сервере **{guild.name}** "
                                f"({timeout_minutes} мин.) истекло.\n"
                                "Вы можете зайти снова и пройти верификацию вовремя."
                            ),
                            color=COMBAT_RED,
                        )
                        dm_embed.set_footer(text=UNIFIED_FOOTER)
                        await member.send(embed=dm_embed)
                    except disnake.Forbidden:
                        pass

                    await member.kick(
                        reason=f"Не прошёл верификацию за {timeout_minutes} минут"
                    )
                    embed = disnake.Embed(
                        title="⏳ Исключение (Таймаут верификации)",
                        description=(
                            f"**Участник:** {member.mention} (`{member.id}`)\n"
                            f"**Причина:** Не прошёл верификацию за `{timeout_minutes}` мин."
                        ),
                        color=COMBAT_RED,
                        timestamp=disnake.utils.utcnow(),
                    )
                    embed.set_footer(text=UNIFIED_FOOTER)
                    await send_log(guild, embed)
                    await asyncio.sleep(1.0)
                except disnake.Forbidden:
                    pass
                except disnake.HTTPException:
                    log.exception(
                        "Не удалось кикнуть неверифицированного участника %s", member.id
                    )

            await asyncio.sleep(0)

    @check_unverified_members.before_loop
    async def before_check_unverified(self):
        await self.bot.wait_until_ready()

    @verification.sub_command(
        name="отправить_панель",
        description="Отправить панель верификации",
    )
    @commands.has_guild_permissions(administrator=True)
    async def send_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        title: str = commands.Param(
            name="заголовок", default="🛡️ Верификация на сервере"
        ),
        description: Optional[str] = commands.Param(name="описание", default=None),
        button_label: str = commands.Param(
            name="надпись", default="Пройти верификацию"
        ),
        button_emoji: str = commands.Param(name="эмодзи", default="✅"),
        use_captcha: Optional[bool] = commands.Param(
            name="капча", default=None, description="Включить капчу для новых аккаунтов?"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        if use_captcha is None:
            cfg = await api.get_guild_config(str(inter.guild_id)) or {}
            use_captcha = (cfg.get("security") or {}).get("useCaptcha", True)

        panel_description = description or (
            f"Добро пожаловать на сервер **{inter.guild.name}**!\n"
            "Нажмите кнопку верификации, чтобы подтвердить профиль и получить доступ к каналам."
        )
        embed = disnake.Embed(
            title=title, description=panel_description, color=TACTICAL_GREEN
        )
        if inter.guild.icon:
            embed.set_thumbnail(url=inter.guild.icon.url)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = VerifyView(
            button_label=button_label, button_emoji=button_emoji, use_captcha=use_captcha
        )
        await inter.channel.send(embed=embed, view=view)
        mode = (
            f"с капчей для аккаунтов младше {CAPTCHA_ACCOUNT_DAYS} дн."
            if use_captcha else "в 1 клик"
        )
        await inter.edit_original_response(
            content=f"✅ Панель верификации ({mode}) отправлена."
        )

    @verification.sub_command(
        name="обновить_панель",
        description="Отредактировать панель верификации",
    )
    @commands.has_guild_permissions(administrator=True)
    async def edit_verify_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(
            name="сообщение_id", description="ID сообщения панели в этом канале"
        ),
        title: Optional[str] = commands.Param(
            name="заголовок", default=None, description="Новый заголовок"
        ),
        description: Optional[str] = commands.Param(
            name="описание", default=None, description="Новый текст описания"
        ),
        button_label: Optional[str] = commands.Param(
            name="надпись", default=None, description="Новая надпись на кнопке"
        ),
        button_emoji: Optional[str] = commands.Param(
            name="эмодзи", default=None, description="Новый эмодзи на кнопке"
        ),
        use_captcha: Optional[bool] = commands.Param(
            name="капча", default=None, description="Включить капчу для новых аккаунтов?"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        try:
            message = await inter.channel.fetch_message(int(message_id))
        except (ValueError, disnake.HTTPException):
            await inter.edit_original_response(
                content="❌ Не удалось получить сообщение с таким ID в этом канале."
            )
            return

        if message.author.id != self.bot.user.id or not message.embeds:
            await inter.edit_original_response(content="❌ Это сообщение нельзя отредактировать.")
            return

        old_embed = message.embeds[0]
        embed = disnake.Embed(
            title=title or old_embed.title,
            description=description or old_embed.description,
            color=old_embed.color,
        )
        if old_embed.thumbnail:
            embed.set_thumbnail(url=old_embed.thumbnail.url)
        embed.set_footer(text=UNIFIED_FOOTER)

        old_button = (
            message.components[0].children[0]
            if message.components and message.components[0].children
            else None
        )
        new_label = button_label or (
            old_button.label if old_button and old_button.label else "Пройти верификацию"
        )
        new_emoji = button_emoji or (
            str(old_button.emoji) if old_button and old_button.emoji else "✅"
        )
        if use_captcha is None:
            use_captcha = getattr(old_button, "custom_id", "") == "persistent_verify_captcha"

        view = VerifyView(
            button_label=new_label,
            button_emoji=new_emoji,
            use_captcha=use_captcha,
        )
        await message.edit(content=None, embed=embed, view=view)
        await inter.edit_original_response(content="✅ Панель верификации обновлена.")


def setup(bot: commands.Bot):
    bot.add_cog(Verification(bot))