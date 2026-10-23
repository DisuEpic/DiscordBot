import disnake
from typing import List, Dict, Any
from api import api
from utils import parse_emoji, add_chunked_role_fields
from config import P3_BLUE, UNIFIED_FOOTER

class VerifyView(disnake.ui.View):
    def __init__(self, button_label: str = "Инициализировать допуск", button_emoji: str = "🤖"):
        super().__init__(timeout=None)
        self.add_item(disnake.ui.Button(
            label=button_label,
            style=disnake.ButtonStyle.success,
            emoji=parse_emoji(button_emoji) or "🤖",
            custom_id="persistent_verify_button"
        ))

def build_role_buttons_view(roles_subset: List[Dict[str, Any]], button_style: disnake.ButtonStyle = disnake.ButtonStyle.secondary) -> disnake.ui.View:
    view = disnake.ui.View(timeout=None)
    for r in roles_subset[:25]:
        emoji = parse_emoji(r.get("emoji"))
        view.add_item(disnake.ui.Button(
            label=r["name"][:80],
            emoji=emoji,
            style=button_style,
            custom_id=f"toggle_role_{r['roleId']}"
        ))
    return view
class ConfirmResetView(disnake.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id

    @disnake.ui.button(label="Да, сбросить", style=disnake.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.defer()
        reset_payload = {
            "guildId": str(inter.guild_id),
            "verificationRoleId": None,
            "welcomeChannelId": None,
            "logChannelId": None,
            "trapChannelId": None
        }

        if await api.save_guild_config(reset_payload):
            await inter.edit_original_response(
                content="♻️ Все настройки безопасности сервера полностью сброшены к начальным.",
                embed=None,
                view=None
            )
        else:
            await inter.edit_original_response(
                content="❌ Не удалось сбросить настройки: API недоступен.",
                embed=None,
                view=None
            )

    @disnake.ui.button(label="Отмена", style=disnake.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return
        await inter.response.edit_message(content=None, view=SettingsDashboardView(self.author_id))
class SettingsDashboardView(disnake.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    @disnake.ui.button(label="Список ролей в БД", style=disnake.ButtonStyle.primary, emoji="📋")
    async def view_roles(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может просматривать эту панель.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))
        guild_roles = [r for r in all_roles if str(r.get("roleId", "")).isdigit() and inter.guild.get_role(int(r["roleId"]))]

        if not guild_roles:
            await inter.edit_original_response(content="⚠️ В базе данных пока нет добавленных ролей для этого сервера.")
            return

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for r in guild_roles:
            cat = r.get("category") or "Общие"
            categories.setdefault(cat, []).append(r)

        embed = disnake.Embed(
            title="📋 Роли сервера, сохраненные в базе данных",
            description="Список доступных ролей по категориям:",
            color=P3_BLUE
        )
        for cat_name, r_list in categories.items():
            add_chunked_role_fields(embed, f"📁 {cat_name}", r_list)
        embed.set_footer(text=UNIFIED_FOOTER)

        await inter.edit_original_response(embed=embed)

    @disnake.ui.button(label="Отключить ловушку", style=disnake.ButtonStyle.secondary, emoji="🤫")
    async def disable_trap(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.defer()
        guild_id = str(inter.guild_id)
        cfg = await api.get_guild_config(guild_id) or {}
        cfg["guildId"] = guild_id
        cfg["trapChannelId"] = None

        if await api.save_guild_config(cfg):
            await inter.edit_original_response(
                content="✅ Канал-тишина успешно отключен. Теперь писать в него безопасно.",
                embed=None,
                view=None
            )
        else:
            await inter.edit_original_response(content="❌ Не удалось сохранить настройки: API недоступен.")
    @disnake.ui.button(label="Сбросить всё (Reset)", style=disnake.ButtonStyle.danger, emoji="♻️")
    async def full_reset(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.edit_message(
            content="⚠️ **Вы уверены?** Будут сброшены роль верификации, каналы приветствий, логов и ловушка. Действие необратимо.",
            view=ConfirmResetView(self.author_id)
        )