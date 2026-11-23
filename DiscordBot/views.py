from typing import Any, Dict, List

import disnake

from api import api
from config import BRAND_COLOR, UNIFIED_FOOTER
from utils import add_chunked_role_fields, parse_emoji


class VerifyView(disnake.ui.View):
    def __init__(
        self,
        button_label: str = "Пройти верификацию",
        button_emoji: str = "✅",
        use_captcha: bool = False,
    ):
        super().__init__(timeout=None)
        custom_id = "persistent_verify_captcha" if use_captcha else "persistent_verify_button"
        self.add_item(
            disnake.ui.Button(
                label=button_label,
                style=disnake.ButtonStyle.success,
                emoji=parse_emoji(button_emoji) or "✅",
                custom_id=custom_id,
            )
        )


def build_role_buttons_view(
    roles_subset: List[Dict[str, Any]],
    button_style: disnake.ButtonStyle = disnake.ButtonStyle.secondary,
    single_choice: bool = False,
) -> disnake.ui.View:
    view = disnake.ui.View(timeout=None)
    prefix = "radio_role_" if single_choice else "toggle_role_"

    for role in roles_subset[:25]:
        view.add_item(
            disnake.ui.Button(
                label=role["name"][:80],
                emoji=parse_emoji(role.get("emoji")),
                style=button_style,
                custom_id=f"{prefix}{role['roleId']}",
            )
        )

    return view


class ConfirmResetView(disnake.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id

    @disnake.ui.button(
        label="Подтвердить сброс", style=disnake.ButtonStyle.danger, emoji="⚠️"
    )
    async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message(
                "❌ Только автор команды может управлять этой панелью.", ephemeral=True
            )
            return

        await inter.response.defer()
        if await api.reset_guild_config(str(inter.guild_id)):
            await inter.edit_original_response(
                content="♻️ Настройки Mirei, управляемые этой панелью, сброшены.",
                embed=None,
                view=None,
            )
        else:
            await inter.edit_original_response(
                content="❌ API не подтвердило сброс настроек.",
                embed=None,
                view=None,
            )

    @disnake.ui.button(label="Отмена", style=disnake.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message(
                "❌ Только автор команды может управлять этой панелью.", ephemeral=True
            )
            return

        await inter.response.edit_message(
            content=None, view=SettingsDashboardView(self.author_id)
        )


class SettingsDashboardView(disnake.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id

    @disnake.ui.select(
        placeholder="Отключить или сбросить настройку",
        options=[
            disnake.SelectOption(
                label="Отключить роль верификации",
                value="verificationRoleId",
                emoji="🛡️",
            ),
            disnake.SelectOption(
                label="Отключить канал приветствий",
                value="welcomeChannelId",
                emoji="👋",
            ),
            disnake.SelectOption(
                label="Отключить канал журнала",
                value="logChannelId",
                emoji="📜",
            ),
            disnake.SelectOption(
                label="Отключить временные голосовые комнаты",
                value="voiceGeneratorChannelId",
                emoji="🔊",
            ),
            disnake.SelectOption(
                label="Сбросить шаблон имени комнат",
                value="voiceRoomTemplate",
                emoji="🏷️",
            ),
            disnake.SelectOption(
                label="Отключить канал-ловушку",
                value="trapChannelId",
                emoji="🤫",
            ),
            disnake.SelectOption(
                label="Сбросить текст приветствия",
                value="welcomeText",
                emoji="📝",
            ),
            disnake.SelectOption(
                label="Сбросить настройки ИИ",
                value="aiReset",
                emoji="💠",
            ),
        ],
    )
    async def remove_single_config(
        self, select: disnake.ui.Select, inter: disnake.MessageInteraction
    ):
        if inter.author.id != self.author_id:
            await inter.response.send_message(
                "❌ Только автор команды может управлять этой панелью.", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        cfg = await api.get_guild_config_for_update(guild_id)
        if cfg is None:
            await inter.edit_original_response(
                content="API не вернуло настройки. Повтори попытку."
            )
            return

        choice = select.values[0]
        labels = {
            "verificationRoleId": "🛡️ Роль верификации отключена.",
            "welcomeChannelId": "👋 Канал приветствий отключён.",
            "logChannelId": "📜 Канал журнала отключён.",
            "voiceGeneratorChannelId": "🔊 Создание временных комнат отключено.",
            "voiceRoomTemplate": "🏷️ Шаблон имени комнат сброшен.",
            "trapChannelId": "🤫 Канал-ловушка отключён.",
            "welcomeText": "📝 Текст приветствия сброшен.",
            "aiReset": "💠 Настройки ИИ сброшены.",
        }

        saved = False
        if choice in ("verificationRoleId", "trapChannelId"):
            security = dict(cfg.get("security") or {})
            security[choice] = None
            saved = await api.update_security_config(guild_id, security)

        elif choice in ("welcomeChannelId", "welcomeText"):
            welcome = dict(cfg.get("welcome") or {})
            if choice == "welcomeChannelId":
                welcome["channelId"] = None
            else:
                welcome["title"] = None
                welcome["description"] = None
            saved = await api.update_welcome_config(guild_id, welcome)

        elif choice == "logChannelId":
            saved = await api.update_general_config(guild_id, None)

        elif choice in ("voiceGeneratorChannelId", "voiceRoomTemplate"):
            voice = dict(cfg.get("voice") or {})
            field = "generatorChannelId" if choice == "voiceGeneratorChannelId" else "roomTemplate"
            voice[field] = None
            saved = await api.update_voice_config(guild_id, voice)

        elif choice == "aiReset":
            saved = await api.update_ai_config(
                guild_id,
                {
                    "enabled": True,
                    "provider": "auto",
                    "autoReplyChance": 0,
                    "customScenario": None,
                    "customRules": None,
                },
            )

        if saved:
            await inter.edit_original_response(
                content=f"✅ {labels[choice]} Вызови `/settings`, чтобы обновить панель."
            )
        else:
            await inter.edit_original_response(
                content="❌ API не подтвердило сохранение настройки."
            )

    @disnake.ui.button(label="Список ролей в БД", style=disnake.ButtonStyle.primary, emoji="📋")
    async def view_roles(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message(
                "❌ Только автор команды может просматривать эту панель.", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        all_roles = await api.get_roles(str(inter.guild_id))
        guild_roles = [
            role
            for role in all_roles
            if str(role.get("roleId", "")).isdigit()
            and inter.guild.get_role(int(role["roleId"]))
        ]

        if not guild_roles:
            await inter.edit_original_response(
                content="⚠️ В каталоге этого сервера пока нет добавленных ролей."
            )
            return

        categories: Dict[str, List[Dict[str, Any]]] = {}
        for role in guild_roles:
            categories.setdefault(role.get("category") or "Общие", []).append(role)

        embed = disnake.Embed(
            title="📋 Роли сервера, сохранённые в базе данных",
            description="Роли по категориям:",
            color=BRAND_COLOR,
        )
        for category, roles in categories.items():
            add_chunked_role_fields(embed, f"📁 {category}", roles)
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @disnake.ui.button(
        label="Сбросить настройки", style=disnake.ButtonStyle.danger, emoji="♻️"
    )
    async def full_reset(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message(
                "❌ Только автор команды может управлять этой панелью.", ephemeral=True
            )
            return

        await inter.response.edit_message(
            content=(
                "⚠️ Сбросить настройки Mirei, управляемые этой панелью? "
                "Фильтры Discord AutoMod управляются через `/automod`."
            ),
            view=ConfirmResetView(self.author_id),
        )