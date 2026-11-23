import asyncio
from typing import Any, Dict, List, Optional

import disnake
from disnake.ext import commands

from api import api
from cogs.audit import is_safe_to_restore_role
from config import BRAND_COLOR, GUILD_ONLY, UNIFIED_FOOTER
from utils import add_chunked_role_fields, check_role_target
from views import build_role_buttons_view


MAX_ROLES_PER_CATEGORY = 25
SAFE_MENTIONS = disnake.AllowedMentions.none()


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    async def _finish(inter: disnake.ApplicationCommandInteraction):
        try:
            await inter.delete_original_response()
        except disnake.NotFound:
            pass

    @staticmethod
    async def _error(inter: disnake.ApplicationCommandInteraction, message: str):
        await inter.edit_original_response(
            content=message, allowed_mentions=SAFE_MENTIONS
        )

    @commands.Cog.listener("on_button_click")
    async def on_role_button(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id or ""
        if not custom_id.startswith(("toggle_role_", "radio_role_")):
            return
        if inter.guild is None or not isinstance(inter.author, disnake.Member):
            return

        await inter.response.defer(with_message=False)

        role_id = custom_id.rsplit("_", 1)[-1]
        role = inter.guild.get_role(int(role_id)) if role_id.isdecimal() else None
        if role is None:
            await inter.followup.send(
                "⚠️ Данная роль больше не существует на сервере.",
                ephemeral=True,
                allowed_mentions=SAFE_MENTIONS,
            )
            return

        catalog = await api.get_roles(str(inter.guild.id), fresh=True)
        allowed_ids = {str(item.get("roleId")) for item in catalog}
        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        if role_id not in allowed_ids or not is_safe_to_restore_role(role, bot_top_role):
            await inter.followup.send(
                "⚠️ Эта роль больше недоступна для выбора.",
                ephemeral=True,
                allowed_mentions=SAFE_MENTIONS,
            )
            return

        member = inter.author
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Снятие роли по кнопке")
                return

            if custom_id.startswith("radio_role_") and inter.message:
                panel_role_ids = set()
                for row in inter.message.components:
                    for component in row.children:
                        component_id = getattr(component, "custom_id", "") or ""
                        if component_id.startswith("radio_role_"):
                            panel_role_ids.add(component_id.rsplit("_", 1)[-1])

                roles_to_remove = [
                    old_role
                    for old_role in member.roles
                    if old_role.id != role.id
                    and str(old_role.id) in panel_role_ids
                    and str(old_role.id) in allowed_ids
                    and is_safe_to_restore_role(old_role, bot_top_role)
                ]
                if roles_to_remove:
                    await member.remove_roles(
                        *roles_to_remove, reason="Смена одиночной роли в панели"
                    )

            await member.add_roles(role, reason="Получение роли по кнопке")

        except disnake.Forbidden:
            await inter.followup.send(
                "⚠️ Ошибка прав: роль бота должна находиться выше этой роли в настройках сервера.",
                ephemeral=True,
                allowed_mentions=SAFE_MENTIONS,
            )
        except disnake.HTTPException:
            await inter.followup.send(
                "❌ Discord не подтвердил изменение роли.",
                ephemeral=True,
                allowed_mentions=SAFE_MENTIONS,
            )

    @commands.slash_command(
        contexts=GUILD_ONLY, name="роли", description="Управление ролями"
    )
    @commands.default_member_permissions(manage_roles=True)
    async def roles(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @roles.sub_command_group(name="панель")
    async def role_panel(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @roles.sub_command(
        name="выдать", description="Выдать роль участнику (для модераторов)"
    )
    @commands.has_guild_permissions(manage_roles=True)
    async def give_role_cmd(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(name="участник"),
        role: disnake.Role = commands.Param(name="роль"),
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_role_target(inter, member, role):
            await self._error(inter, error_msg)
            return

        try:
            await member.add_roles(role, reason=f"Выдано модератором {inter.author}")
            await self._finish(inter)
        except disnake.Forbidden:
            await self._error(inter, "⚠️ Роль бота должна стоять выше выдаваемой роли.")

    @roles.sub_command(
        name="снять", description="Снять роль с участника (для модераторов)"
    )
    @commands.has_guild_permissions(manage_roles=True)
    async def take_role_cmd(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(name="участник"),
        role: disnake.Role = commands.Param(name="роль"),
    ):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_role_target(inter, member, role):
            await self._error(inter, error_msg)
            return

        try:
            await member.remove_roles(role, reason=f"Снято модератором {inter.author}")
            await self._finish(inter)
        except disnake.Forbidden:
            await self._error(inter, "⚠️ Роль бота должна стоять выше снимаемой роли.")

    @roles.sub_command(
        name="добавить", description="Добавить роль в базу данных с категорией"
    )
    @commands.has_guild_permissions(administrator=True)
    async def add_role(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role = commands.Param(name="роль"),
        category: str = commands.Param(
            name="категория", description="Например: Игры, Уведомления, Пол, Цвета"
        ),
        emoji: str = commands.Param(
            name="эмодзи", description="Смайлик для кнопки (например: 🎮)"
        ),
        custom_name: Optional[str] = commands.Param(
            name="название", default=None, description="Свое название"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        if not is_safe_to_restore_role(role, bot_top_role):
            await self._error(inter, "Эта роль не подходит для самостоятельной выдачи.")
            return

        clean_category = category.strip() or "Общие"
        existing_roles = await api.get_roles(guild_id)
        category_roles = [
            item for item in existing_roles
            if (item.get("category") or "Общие").lower() == clean_category.lower()
            and str(item.get("roleId")) != str(role.id)
        ]
        if len(category_roles) >= MAX_ROLES_PER_CATEGORY:
            await self._error(
                inter,
                f"⚠️ В категории **«{clean_category}»** уже достигнут лимит "
                f"в **{MAX_ROLES_PER_CATEGORY}** ролей.",
            )
            return

        name = custom_name if custom_name else role.name
        if await api.add_role(
            guild_id=guild_id,
            category=clean_category,
            emoji=emoji,
            role_id=str(role.id),
            name=name,
        ):
            await self._finish(inter)
        else:
            await self._error(inter, "❌ Ошибка при сохранении роли в API.")

    @roles.sub_command(name="удалить", description="Удалить роль из базы данных")
    @commands.has_guild_permissions(administrator=True)
    async def delete_role(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role = commands.Param(name="роль"),
    ):
        await inter.response.defer(ephemeral=True)
        if await api.delete_role(str(inter.guild_id), str(role.id)):
            await self._finish(inter)
        else:
            await self._error(inter, "❌ Роль не найдена в базе данных.")

    @roles.sub_command(
        name="очистить_категорию", description="Удалить ВСЕ роли категории из базы"
    )
    @commands.has_guild_permissions(administrator=True)
    async def clear_category_roles(
        self,
        inter: disnake.ApplicationCommandInteraction,
        category: str = commands.Param(name="категория"),
    ):
        await inter.response.defer(ephemeral=True)
        if await api.delete_category_roles(str(inter.guild_id), category):
            await self._finish(inter)
        else:
            await self._error(inter, f"❌ В категории **«{category}»** не найдено ролей.")

    @role_panel.sub_command(
        name="отправить", description="Отправить блок выбора ролей одной категории"
    )
    @commands.has_guild_permissions(administrator=True)
    async def send_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        category: str = commands.Param(
            name="категория", description="Какую категорию отправить"
        ),
        title: Optional[str] = commands.Param(
            name="заголовок", default=None, description="Заголовок"
        ),
        description: Optional[str] = commands.Param(
            name="описание", default=None, description="Описание"
        ),
        single_choice: bool = commands.Param(
            name="одна_роль",
            default=False,
            description="Разрешить выбрать только ОДНУ роль из этого блока? (например, Пол или Цвет)",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))
        target_roles = [
            item for item in all_roles
            if (item.get("category") or "Общие").lower() == category.lower()
            and str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await self._error(inter, f"⚠️ В категории **«{category}»** нет добавленных ролей.")
            return

        embed = disnake.Embed(
            title=title or f"🎭 Выбор ролей: {category}",
            description=description or "Нажмите на кнопку для получения/снятия роли:",
            color=BRAND_COLOR,
        )
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles, single_choice=single_choice)
        await inter.channel.send(embed=embed, view=view, allowed_mentions=SAFE_MENTIONS)
        await self._finish(inter)

    @role_panel.sub_command(
        name="отправить_все", description="Отправить все категории ролей отдельными блоками"
    )
    @commands.has_guild_permissions(administrator=True)
    async def send_all_categories(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))

        guild_roles = [
            item for item in all_roles
            if str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ]
        if not guild_roles:
            await self._error(inter, "⚠️ В базе данных пока нет добавленных ролей.")
            return

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for item in guild_roles:
            category = item.get("category") or "Общие"
            categories.setdefault(category, []).append(item)

        for category, items in categories.items():
            subset = items[:MAX_ROLES_PER_CATEGORY]
            embed = disnake.Embed(
                title=f"🎭 Выбор ролей: {category}",
                description="Выберите необходимые роли с помощью кнопок ниже:",
                color=BRAND_COLOR,
            )
            add_chunked_role_fields(embed, "Доступные роли:", subset)
            embed.set_footer(text=UNIFIED_FOOTER)
            view = build_role_buttons_view(subset, single_choice=False)
            await inter.channel.send(
                embed=embed, view=view, allowed_mentions=SAFE_MENTIONS
            )
            await asyncio.sleep(0.3)

        await self._finish(inter)

    @role_panel.sub_command(
        name="обновить", description="Обновить роли и текст в уже отправленном блоке ролей"
    )
    @commands.has_guild_permissions(administrator=True)
    async def edit_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(
            name="сообщение_id", description="ID сообщения блока ролей в этом канале"
        ),
        category: str = commands.Param(
            name="категория", description="Категория ролей из базы для этого блока"
        ),
        title: Optional[str] = commands.Param(
            name="заголовок", default=None, description="Новый заголовок"
        ),
        description: Optional[str] = commands.Param(
            name="описание", default=None, description="Новое описание"
        ),
        single_choice: Optional[bool] = commands.Param(
            name="одна_роль",
            default=None,
            description="Разрешить выбрать только ОДНУ роль из этого блока?",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        try:
            msg = await inter.channel.fetch_message(int(message_id))
        except Exception:
            await self._error(inter, "❌ Сообщение с таким ID не найдено в этом канале.")
            return

        if msg.author.id != self.bot.user.id:
            await self._error(
                inter, "❌ Можно редактировать только сообщения, отправленные ботом."
            )
            return

        all_roles = await api.get_roles(str(inter.guild_id))
        target_roles = [
            item for item in all_roles
            if (item.get("category") or "Общие").lower() == category.lower()
            and str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await self._error(inter, f"⚠️ В категории **«{category}»** нет актуальных ролей.")
            return

        if single_choice is None:
            was_radio = False
            if msg.components and msg.components[0].children:
                first_cid = getattr(msg.components[0].children[0], "custom_id", "") or ""
                was_radio = first_cid.startswith("radio_role_")
            use_single_choice = was_radio
        else:
            use_single_choice = single_choice

        old_embed = msg.embeds[0] if msg.embeds else None
        embed_title = title or (old_embed.title if old_embed else f"🎭 Выбор ролей: {category}")
        embed_desc = description or (
            old_embed.description if old_embed else "Нажмите на кнопку для выбора:"
        )

        embed = disnake.Embed(
            title=embed_title, description=embed_desc, color=BRAND_COLOR
        )
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles, single_choice=use_single_choice)
        await msg.edit(
            content=None, embed=embed, view=view, allowed_mentions=SAFE_MENTIONS
        )
        await self._finish(inter)


def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))