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


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_button_click")
    async def on_role_button(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id or ""
        if not custom_id.startswith(("toggle_role_", "radio_role_")):
            return
        if inter.guild is None or not isinstance(inter.author, disnake.Member):
            return

        await inter.response.defer(ephemeral=True)
        is_radio = custom_id.startswith("radio_role_")
        role_id = custom_id.rsplit("_", 1)[-1]
        role = inter.guild.get_role(int(role_id)) if role_id.isdecimal() else None

        if role is None:
            await inter.edit_original_response(
                content="⚠️ Эта роль больше не существует на сервере."
            )
            return

        catalog = await api.get_roles(str(inter.guild.id), fresh=True)
        allowed_ids = {str(item.get("roleId")) for item in catalog}
        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        if role_id not in allowed_ids or not is_safe_to_restore_role(role, bot_top_role):
            await inter.edit_original_response(
                content="Эта роль сейчас недоступна для самостоятельного выбора."
            )
            return

        member = inter.author
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Снятие роли по кнопке")
            else:
                if is_radio and inter.message:
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
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав. Проверьте порядок ролей."
            )
            return
        except disnake.HTTPException:
            await inter.edit_original_response(
                content="Discord не подтвердил изменение ролей. Проверьте результат и повторите."
            )
            return

        await inter.edit_original_response(content=f"Роль обновлена: {role.mention}")

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="give_role",
        description="Выдать роль участнику",
    )
    @commands.default_member_permissions(manage_roles=True)
    async def give_role_cmd(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        role: disnake.Role,
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_role_target(inter, member, role):
            await inter.edit_original_response(content=error)
            return

        try:
            await member.add_roles(role, reason=f"Выдано модератором {inter.author}")
            await inter.edit_original_response(
                content=f"✅ Роль {role.mention} выдана участнику {member.mention}."
            )
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ Роль бота должна стоять выше выдаваемой роли."
            )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="take_role",
        description="Снять роль с участника",
    )
    @commands.default_member_permissions(manage_roles=True)
    async def take_role_cmd(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        role: disnake.Role,
    ):
        await inter.response.defer(ephemeral=True)
        if error := check_role_target(inter, member, role):
            await inter.edit_original_response(content=error)
            return

        try:
            await member.remove_roles(role, reason=f"Снято модератором {inter.author}")
            await inter.edit_original_response(
                content=f"✅ Роль {role.mention} снята с участника {member.mention}."
            )
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ Роль бота должна стоять выше снимаемой роли."
            )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="add_role",
        description="Добавить роль в каталог с категорией",
    )
    @commands.default_member_permissions(administrator=True)
    async def add_role(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        category: str = commands.Param(description="Например: Игры, Уведомления, Цвета"),
        emoji: str = commands.Param(description="Эмодзи кнопки, например 🎮"),
        custom_name: Optional[str] = commands.Param(
            default=None, description="Название на кнопке"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)

        bot_top_role = inter.guild.me.top_role if inter.guild.me else None
        if not is_safe_to_restore_role(role, bot_top_role):
            await inter.edit_original_response(
                content="Эта роль не подходит для самостоятельной выдачи."
            )
            return

        clean_category = category.strip() or "Общие"
        existing_roles = await api.get_roles(guild_id)
        category_roles = [
            item
            for item in existing_roles
            if (item.get("category") or "Общие").lower() == clean_category.lower()
            and str(item.get("roleId")) != str(role.id)
        ]
        if len(category_roles) >= MAX_ROLES_PER_CATEGORY:
            await inter.edit_original_response(
                content=(
                    f"⚠️ В категории **«{clean_category}»** достигнут лимит "
                    f"в **{MAX_ROLES_PER_CATEGORY}** ролей."
                )
            )
            return

        name = custom_name or role.name
        saved = await api.add_role(
            guild_id=guild_id,
            category=clean_category,
            emoji=emoji,
            role_id=str(role.id),
            name=name,
        )
        if saved:
            await inter.edit_original_response(
                content=(
                    f"✅ Роль {role.mention} сохранена в категории "
                    f"**«{clean_category}»** под именем **{name}**."
                )
            )
        else:
            await inter.edit_original_response(content="❌ API не подтвердило сохранение роли.")

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="delete_role",
        description="Удалить роль из каталога",
    )
    @commands.default_member_permissions(administrator=True)
    async def delete_role(
        self, inter: disnake.ApplicationCommandInteraction, role: disnake.Role
    ):
        await inter.response.defer(ephemeral=True)
        if await api.delete_role(str(inter.guild_id), str(role.id)):
            await inter.edit_original_response(
                content=f"🗑️ Роль {role.mention} удалена из каталога."
            )
        else:
            await inter.edit_original_response(content="❌ API не подтвердило удаление роли.")

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="clear_category_roles",
        description="Удалить все роли категории из каталога",
    )
    @commands.default_member_permissions(administrator=True)
    async def clear_category_roles(
        self, inter: disnake.ApplicationCommandInteraction, category: str
    ):
        await inter.response.defer(ephemeral=True)
        if await api.delete_category_roles(str(inter.guild_id), category):
            await inter.edit_original_response(
                content=f"🗑️ Все роли в категории **«{category}»** удалены из каталога."
            )
        else:
            await inter.edit_original_response(
                content=f"❌ API не подтвердило очистку категории **«{category}»**."
            )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="send_category_panel",
        description="Отправить панель выбора ролей одной категории",
    )
    @commands.default_member_permissions(administrator=True)
    async def send_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        category: str = commands.Param(description="Какую категорию отправить"),
        title: Optional[str] = commands.Param(default=None, description="Заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Описание"),
        single_choice: bool = commands.Param(
            default=False, description="Разрешить выбрать одну роль из этого блока"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))
        target_roles = [
            item
            for item in all_roles
            if (item.get("category") or "Общие").lower() == category.lower()
            and str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await inter.edit_original_response(
                content=f"⚠️ В категории **«{category}»** нет добавленных ролей."
            )
            return

        embed = disnake.Embed(
            title=title or f"🎭 Выбор ролей: {category}",
            description=description or "Нажмите на кнопку, чтобы получить или снять роль.",
            color=BRAND_COLOR,
        )
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles, single_choice=single_choice)
        await inter.channel.send(embed=embed, view=view)

        mode = "одна роль" if single_choice else "несколько ролей"
        await inter.edit_original_response(
            content=f"✅ Панель **«{category}»** опубликована. Режим выбора: {mode}."
        )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="send_all_categories",
        description="Отправить все категории ролей отдельными панелями",
    )
    @commands.default_member_permissions(administrator=True)
    async def send_all_categories(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))
        guild_roles = [
            item
            for item in all_roles
            if str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ]
        if not guild_roles:
            await inter.edit_original_response(
                content="⚠️ В каталоге пока нет добавленных ролей."
            )
            return

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for item in guild_roles:
            category = item.get("category") or "Общие"
            categories.setdefault(category, []).append(item)

        for category, roles in categories.items():
            subset = roles[:MAX_ROLES_PER_CATEGORY]
            embed = disnake.Embed(
                title=f"🎭 Выбор ролей: {category}",
                description="Выберите роли с помощью кнопок ниже.",
                color=BRAND_COLOR,
            )
            add_chunked_role_fields(embed, "Доступные роли:", subset)
            embed.set_footer(text=UNIFIED_FOOTER)

            view = build_role_buttons_view(subset)
            await inter.channel.send(embed=embed, view=view)
            await asyncio.sleep(0.3)

        await inter.edit_original_response(
            content=f"✅ Опубликовано панелей: **{len(categories)}**."
        )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="edit_category_panel",
        description="Обновить роли и текст в опубликованной панели",
    )
    @commands.default_member_permissions(administrator=True)
    async def edit_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(description="ID сообщения панели в этом канале"),
        category: str = commands.Param(description="Категория ролей для панели"),
        title: Optional[str] = commands.Param(default=None, description="Новый заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Новое описание"),
        single_choice: Optional[bool] = commands.Param(
            default=None, description="Разрешить выбрать одну роль из этого блока"
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

        if message.author.id != self.bot.user.id:
            await inter.edit_original_response(
                content="❌ Можно редактировать только сообщения, отправленные ботом."
            )
            return

        all_roles = await api.get_roles(str(inter.guild_id))
        target_roles = [
            item
            for item in all_roles
            if (item.get("category") or "Общие").lower() == category.lower()
            and str(item.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(item["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await inter.edit_original_response(
                content=f"⚠️ В категории **«{category}»** нет актуальных ролей."
            )
            return

        if single_choice is None:
            first_component = (
                message.components[0].children[0]
                if message.components and message.components[0].children
                else None
            )
            first_id = getattr(first_component, "custom_id", "") or ""
            single_choice = first_id.startswith("radio_role_")

        old_embed = message.embeds[0] if message.embeds else None
        embed_title = title or (old_embed.title if old_embed else f"🎭 Выбор ролей: {category}")
        embed_description = description or (
            old_embed.description if old_embed else "Нажмите на кнопку для выбора."
        )
        embed = disnake.Embed(
            title=embed_title, description=embed_description, color=BRAND_COLOR
        )
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles, single_choice=single_choice)
        await message.edit(content=None, embed=embed, view=view)
        mode = "одна роль" if single_choice else "несколько ролей"
        await inter.edit_original_response(
            content=f"✅ Панель **«{category}»** обновлена. Режим выбора: {mode}."
        )


def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))