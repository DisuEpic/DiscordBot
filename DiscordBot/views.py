import disnake
from typing import List, Dict, Any
from api import api
from utils import parse_emoji, add_chunked_role_fields
from config import BRAND_COLOR, UNIFIED_FOOTER


class VerifyView(disnake.ui.View):
    def __init__(
        self,
        button_label: str = "Пройти верификацию",
        button_emoji: str = "✅",
        use_captcha: bool = False
    ):
        super().__init__(timeout=None)
        custom_id = "persistent_verify_captcha" if use_captcha else "persistent_verify_button"
        self.add_item(disnake.ui.Button(
            label=button_label,
            style=disnake.ButtonStyle.success,
            emoji=parse_emoji(button_emoji) or "✅",
            custom_id=custom_id
        ))


def build_role_buttons_view(
    roles_subset: List[Dict[str, Any]],
    button_style: disnake.ButtonStyle = disnake.ButtonStyle.secondary,
    single_choice: bool = False
) -> disnake.ui.View:
    view = disnake.ui.View(timeout=None)
    prefix = "radio_role_" if single_choice else "toggle_role_"
    for r in roles_subset[:25]:
        emoji = parse_emoji(r.get("emoji"))
        view.add_item(disnake.ui.Button(
            label=r["name"][:80],
            emoji=emoji,
            style=button_style,
            custom_id=f"{prefix}{r['roleId']}"
        ))
    return view


class ConfirmResetView(disnake.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id

    @disnake.ui.button(label="Да, сбросить всё", style=disnake.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.defer()
        if await api.reset_guild_config(str(inter.guild_id)):
            await inter.edit_original_response(
                content="♻️ Все настройки сервера полностью сброшены к начальным.",
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

    @disnake.ui.select(
        placeholder="🗑️ Отключить / очистить отдельный параметр...",
        options=[
            disnake.SelectOption(label="Отключить роль верификации", value="verificationRoleId", emoji="🛡️"),
            disnake.SelectOption(label="Отключить канал приветствий", value="welcomeChannelId", emoji="👋"),
            disnake.SelectOption(label="Отключить канал аудита (логов)", value="logChannelId", emoji="📜"),
            disnake.SelectOption(label="Отключить приватные войсы", value="voiceGeneratorChannelId", emoji="🔊"),
            disnake.SelectOption(label="Сбросить шаблон имени войсов", value="voiceRoomTemplate", emoji="🏷️"),
            disnake.SelectOption(label="Отключить канал-ловушку (Тишина)", value="trapChannelId", emoji="🤫"),
            disnake.SelectOption(label="Сбросить текст шаблона приветствия", value="welcomeText", emoji="📝"),
            disnake.SelectOption(label="Сбросить настройки ИИ к стандартным", value="aiReset", emoji="💠"),
        ]
    )
    async def remove_single_config(self, select: disnake.ui.Select, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        cfg = await api.get_guild_config(guild_id) or {}

        choice = select.values[0]
        labels_map = {
            "verificationRoleId": "🛡️ Роль верификации отключена.",
            "welcomeChannelId": "👋 Канал приветствий отключен.",
            "logChannelId": "📜 Канал аудита (логов) отключен.",
            "voiceGeneratorChannelId": "🔊 Создание приватных голосовых комнат отключено.",
            "voiceRoomTemplate": "🏷️ Шаблон имени приватных войсов сброшен.",
            "trapChannelId": "🤫 Канал-ловушка (Тишина) отключен.",
            "welcomeText": "📝 Текст приветствия сброшен к стандартному.",
            "aiReset": "💠 Настройки ИИ сброшены к стандартным."
        }

        ok = False
        if choice in ("verificationRoleId", "trapChannelId"):
            sec = dict(cfg.get("security") or {})
            sec[choice] = None
            ok = await api.update_security_config(guild_id, sec)
        elif choice == "welcomeChannelId":
            wel = dict(cfg.get("welcome") or {})
            wel["channelId"] = None
            ok = await api.update_welcome_config(guild_id, wel)
        elif choice == "welcomeText":
            wel = dict(cfg.get("welcome") or {})
            wel["title"] = None
            wel["description"] = None
            ok = await api.update_welcome_config(guild_id, wel)
        elif choice == "logChannelId":
            ok = await api.update_general_config(guild_id, None)
        elif choice == "voiceGeneratorChannelId":
            voi = dict(cfg.get("voice") or {})
            voi["generatorChannelId"] = None
            ok = await api.update_voice_config(guild_id, voi)
        elif choice == "voiceRoomTemplate":
            voi = dict(cfg.get("voice") or {})
            voi["roomTemplate"] = None
            ok = await api.update_voice_config(guild_id, voi)
        elif choice == "aiReset":
            ok = await api.update_ai_config(guild_id, {
                "enabled": True,
                "provider": "auto",
                "autoReplyChance": 0,
                "customScenario": None,
                "customRules": None,
            })

        if ok:
            await inter.followup.send(f"✅ {labels_map.get(choice, 'Параметр сброшен.')} Вызовите `/settings`, чтобы обновить панель.", ephemeral=True)
        else:
            await inter.followup.send("❌ Не удалось сохранить настройки: API недоступен.", ephemeral=True)

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
            color=BRAND_COLOR
        )
        for cat_name, r_list in categories.items():
            add_chunked_role_fields(embed, f"📁 {cat_name}", r_list)
        embed.set_footer(text=UNIFIED_FOOTER)

        await inter.edit_original_response(embed=embed)

    @disnake.ui.button(label="Сбросить всё (Reset)", style=disnake.ButtonStyle.danger, emoji="♻️")
    async def full_reset(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.response.send_message("❌ Только автор команды может управлять этой панелью.", ephemeral=True)
            return

        await inter.response.edit_message(
            content="⚠️ **Вы уверены?** Будут сброшены все каналы и настройки безопасности сервера. Действие необратимо.",
            view=ConfirmResetView(self.author_id)
        )