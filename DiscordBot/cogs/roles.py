import disnake
from disnake.ext import commands
from typing import Optional, Dict, List, Any
from api import api
from utils import add_chunked_role_fields, check_role_target
from views import build_role_buttons_view
from config import GUILD_ONLY, P3_BLUE, UNIFIED_FOOTER

MAX_ROLES_PER_CATEGORY = 25

class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_button_click")
    async def on_role_button(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id
        if not custom_id.startswith("toggle_role_"):
            return

        # Тихо подтверждаем нажатие кнопки без изменения сообщения
        await inter.response.defer()
        role_id_str = custom_id.replace("toggle_role_", "")
        if not role_id_str.isdigit():
            return

        role = inter.guild.get_role(int(role_id_str))
        if not role:
            return

        member = inter.author
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Снятие роли по кнопке")
            else:
                await member.add_roles(role, reason="Получение роли по кнопке")
        except disnake.Forbidden:
            pass

    @commands.slash_command(contexts=GUILD_ONLY, name="give_role", description="Выдать роль участнику (для модераторов)")
    @commands.default_member_permissions(manage_roles=True)
    async def give_role_cmd(self, inter: disnake.ApplicationCommandInteraction, member: disnake.Member, role: disnake.Role):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_role_target(inter, member, role):
            await inter.edit_original_response(content=error_msg)
            return
        try:
            await member.add_roles(role, reason=f"Выдано модератором {inter.author}")
            await inter.edit_original_response(content=f"✅ Роль {role.mention} успешно выдана участнику {member.mention}.")
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ Роль бота должна стоять выше выдаваемой роли.")

    @commands.slash_command(contexts=GUILD_ONLY, name="take_role", description="Снять роль с участника (для модераторов)")
    @commands.default_member_permissions(manage_roles=True)
    async def take_role_cmd(self, inter: disnake.ApplicationCommandInteraction, member: disnake.Member, role: disnake.Role):
        await inter.response.defer(ephemeral=True)
        if error_msg := check_role_target(inter, member, role):
            await inter.edit_original_response(content=error_msg)
            return
        try:
            await member.remove_roles(role, reason=f"Снято модератором {inter.author}")
            await inter.edit_original_response(content=f"✅ Роль {role.mention} успешно снята с участника {member.mention}.")
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ Роль бота должна стоять выше снимаемой роли.")

    @commands.slash_command(contexts=GUILD_ONLY, name="add_role", description="Добавить роль в базу данных с категорией")
    @commands.default_member_permissions(administrator=True)
    async def add_role(
        self,
        inter: disnake.ApplicationCommandInteraction,
        role: disnake.Role,
        category: str = commands.Param(description="Например: Игры, Уведомления, Платформы"),
        emoji: str = commands.Param(description="Смайлик для кнопки (например: 🎮)"),
        custom_name: Optional[str] = commands.Param(default=None, description="Свое название")
    ):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        clean_category = category.strip() or "Общие"

        existing_roles = await api.get_roles(guild_id)
        category_roles = [
            r for r in existing_roles
            if (r.get("category") or "Общие").lower() == clean_category.lower()
            and str(r.get("roleId")) != str(role.id)
        ]
        if len(category_roles) >= MAX_ROLES_PER_CATEGORY:
            await inter.edit_original_response(
                content=f"⚠️ В категории **«{clean_category}»** уже достигнут лимит в **{MAX_ROLES_PER_CATEGORY}** ролей."
            )
            return

        name = custom_name if custom_name else role.name
        if await api.add_role(guild_id=guild_id, category=clean_category, emoji=emoji, role_id=str(role.id), name=name):
            await inter.edit_original_response(
                content=f"✅ Роль {role.mention} сохранена в категорию **«{clean_category}»** под именем **{name}**!"
            )
        else:
            await inter.edit_original_response(content="❌ Ошибка при сохранении роли в API.")

    @commands.slash_command(contexts=GUILD_ONLY, name="delete_role", description="Удалить роль из базы данных")
    @commands.default_member_permissions(administrator=True)
    async def delete_role(self, inter: disnake.ApplicationCommandInteraction, role: disnake.Role):
        await inter.response.defer(ephemeral=True)
        if await api.delete_role(str(inter.guild_id), str(role.id)):
            await inter.edit_original_response(content=f"🗑️ Роль {role.mention} успешно удалена из базы данных.")
        else:
            await inter.edit_original_response(content="❌ Роль не найдена в базе данных.")

    @commands.slash_command(contexts=GUILD_ONLY, name="clear_category_roles", description="Удалить ВСЕ роли категории из базы")
    @commands.default_member_permissions(administrator=True)
    async def clear_category_roles(self, inter: disnake.ApplicationCommandInteraction, category: str):
        await inter.response.defer(ephemeral=True)
        if await api.delete_category_roles(str(inter.guild_id), category):
            await inter.edit_original_response(content=f"🗑️ Все роли в категории **«{category}»** успешно удалены из базы данных.")
        else:
            await inter.edit_original_response(content=f"❌ В категории **«{category}»** не найдено ролей.")

    @commands.slash_command(contexts=GUILD_ONLY, name="send_category_panel", description="Отправить блок выбора ролей одной категории")
    @commands.default_member_permissions(administrator=True)
    async def send_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        category: str = commands.Param(description="Какую категорию отправить"),
        title: Optional[str] = commands.Param(default=None, description="Заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Описание")
    ):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))

        target_roles = [
            r for r in all_roles
            if (r.get("category") or "Общие").lower() == category.lower()
            and str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await inter.edit_original_response(content=f"⚠️ В категории **«{category}»** нет добавленных ролей.")
            return

        embed = disnake.Embed(title=title or f"🎭 Выбор ролей: {category}", description=description or "Нажмите на кнопку для получения/снятия роли:", color=P3_BLUE)
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles)
        await inter.channel.send(embed=embed, view=view)
        await inter.edit_original_response(content=f"✅ Блок ролей для категории **«{category}»** успешно опубликован!")

    @commands.slash_command(contexts=GUILD_ONLY, name="send_all_categories", description="Отправить все категории ролей отдельными блоками")
    @commands.default_member_permissions(administrator=True)
    async def send_all_categories(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))

        guild_roles = [r for r in all_roles if str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))]
        if not guild_roles:
            await inter.edit_original_response(content="⚠️ В базе данных пока нет добавленных ролей.")
            return

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for r in guild_roles:
            cat = r.get("category") or "Общие"
            categories.setdefault(cat, []).append(r)

        for cat_name, r_list in categories.items():
            subset = r_list[:MAX_ROLES_PER_CATEGORY]
            embed = disnake.Embed(
                title=f"🎭 Выбор ролей: {cat_name}",
                description="Выберите необходимые роли с помощью кнопок ниже:",
                color=P3_BLUE
            )
            add_chunked_role_fields(embed, "Доступные роли:", subset)
            embed.set_footer(text=UNIFIED_FOOTER)
            view = build_role_buttons_view(subset)
            await inter.channel.send(embed=embed, view=view)

        await inter.edit_original_response(content=f"✅ Опубликовано блоков по категориям: **{len(categories)}** шт.")

    @commands.slash_command(contexts=GUILD_ONLY, name="edit_category_panel", description="Обновить роли и текст в уже отправленном блоке ролей")
    @commands.default_member_permissions(administrator=True)
    async def edit_category_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message_id: str = commands.Param(description="ID сообщения блока ролей в этом канале"),
        category: str = commands.Param(description="Категория ролей из базы для этого блока"),
        title: Optional[str] = commands.Param(default=None, description="Новый заголовок"),
        description: Optional[str] = commands.Param(default=None, description="Новое описание")
    ):
        await inter.response.defer(ephemeral=True)
        try:
            msg = await inter.channel.fetch_message(int(message_id))
        except Exception:
            await inter.edit_original_response(content="❌ Сообщение с таким ID не найдено в этом канале.")
            return

        if msg.author.id != self.bot.user.id:
            await inter.edit_original_response(content="❌ Можно редактировать только сообщения, отправленные ботом.")
            return

        all_roles = await api.get_roles(str(inter.guild_id))
        target_roles = [
            r for r in all_roles
            if (r.get("category") or "Общие").lower() == category.lower()
            and str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))
        ][:MAX_ROLES_PER_CATEGORY]

        if not target_roles:
            await inter.edit_original_response(content=f"⚠️ В категории **«{category}»** нет актуальных ролей.")
            return

        old_embed = msg.embeds[0] if msg.embeds else None
        embed_title = title or (old_embed.title if old_embed else f"🎭 Выбор ролей: {category}")
        embed_desc = description or (old_embed.description if old_embed else "Нажмите на кнопку для выбора:")

        embed = disnake.Embed(title=embed_title, description=embed_desc, color=P3_BLUE)
        add_chunked_role_fields(embed, "Доступные роли:", target_roles)
        embed.set_footer(text=UNIFIED_FOOTER)

        view = build_role_buttons_view(target_roles)
        await msg.edit(content=None, embed=embed, view=view)
        await inter.edit_original_response(content=f"✅ Блок ролей для категории **«{category}»** успешно обновлен!")

def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))