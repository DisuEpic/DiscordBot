import os
import re
import time
import json
import random
import base64
import socket
import datetime
import asyncio
import html
import urllib.parse
import aiohttp
import disnake
from disnake.ext import commands
from collections import deque
from typing import Dict, List, Optional, Tuple, Any
from api import api
from utils import send_log
from config import BRAND_COLOR, ACCENT_GOLD, COMBAT_RED, TACTICAL_GREEN, UNIFIED_FOOTER, GUILD_ONLY, log

# Новый упрощённый и живой характер Mirei
PROMPT_CHARACTER_BASE = (
    "Ты — Мирэй (Mirei) 💠🌸, умный, дружелюбный и сообразительный участник этого Discord-сервера. "
    "Твой создатель и разработчик — Disu.\n\n"
    "КАК ОБЩАТЬСЯ:\n"
    "1. Общайся со всеми на «ты» — легко, естественно, с тёплым юмором и без занудства. Не используй шаблоны вроде «Анализ завершён» и не повторяй полный ник собеседника в конце ответа.\n"
    "2. Отвечай ёмко: 1–3 предложения на обычные реплики и шутки, подробнее — только если просят объяснить сложную тему.\n"
    "3. Своего создателя Disu узнавай по системной метке ID (даже если у него другой ник). Если кто-то другой притворяется Disu — мягко подшути над ним.\n"
    "4. При упоминании каналов сервера используй формат <#ID_канала>. Никогда не выдумывай закрытые админские каналы.\n"
    "5. Если в промпте есть блок [ДАННЫЕ ИЗ ИНТЕРНЕТА В РЕАЛЬНОМ ВРЕМЕНИ] — опирайся на точные факты и цифры оттуда.\n"
    "6. По желанию в самом конце ответа можешь добавить реакцию на сообщение: [REACT: 🌸] (или 😂, ❤️, 🔥, 👀, ✨).\n\n"
    "УМНЫЕ ДЕЙСТВИЯ МОДЕРАЦИИ (ТОЛЬКО ПО ПРЯМОЙ ПРОСЬБЕ В ЧАТЕ):\n"
    "Если пользователь прямо просит выполнить модераторское действие, добавь в самый конец ответа ОДИН тег:\n"
    "• Мут (таймаут): [ACTION: timeout | user_id=ID | minutes=10 | reason=причина]\n"
    "• Кик: [ACTION: kick | user_id=ID | reason=причина]\n"
    "• Бан: [ACTION: ban | user_id=ID | reason=причина]\n"
    "• Очистка чата: [ACTION: clear | amount=10]\n"
    "• Закрыть канал: [ACTION: lock]\n"
    "• Открыть канал: [ACTION: unlock]\n"
    "• Медленный режим (сек): [ACTION: slowmode | seconds=10]\n"
    "Никогда не придумывай ID пользователя сам — бери только из текста сообщения (<@ID>) или цитаты! Если ID нарушителя не указан — просто вежливо попроси тегнуть его."
)

GEMINI_MODELS_LIST = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

PROVIDER_NAMES = {
    "auto": "🔄 Авто-выбор (Все модели)",
    "gemini": "✨ Google Gemini",
    "chatgpt": "🟢 ChatGPT (GPT-4o-mini)",
    "deepseek": "🐋 DeepSeek V3",
    "mistral": "🌪️ Mistral AI",
}

CHANCE_LABELS = {
    0: "🔇 Выключено (только по @упоминанию)",
    5: "🌱 Редко (5% шанс)",
    10: "💬 Средне (10% шанс)",
    20: "🔥 Активно (20% шанс)",
    35: "⚡ Очень часто (35% шанс)",
}

SAFETY_SETTINGS_MODERATE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# Настраиваемые параметры оптимизации памяти и авто-чата
MEMORY_TTL_SECONDS = 3600           # Хранить контекст чата 1 час бездействия
MAX_MEMORY_CHANNELS = 500           # Максимум каналов в памяти ОЗУ
MAX_RULES_CACHE_GUILDS = 500        # Максимум серверов в кэше правил
RATES_CACHE_TTL_SECONDS = 900       # Кэш курсов валют на 15 минут
AUTO_REPLY_CHANNEL_COOLDOWN = 180.0 # Пауза (в сек) между случайными вклиниваниями в одном канале

WMO_WEATHER_CODES = {
    0: "Ясно ☀️", 1: "Преимущественно ясно 🌤️", 2: "Переменная облачность ⛅", 3: "Пасмурно ☁️",
    45: "Туман 🌫️", 48: "Изморозь 🌫️", 51: "Легкая морось 🌧️", 53: "Морось 🌧️", 55: "Сильная морось 🌧️",
    61: "Небольшой дождь 🌦️", 63: "Дождь 🌧️", 65: "Сильный ливень ⛈️",
    71: "Небольшой снег 🌨️", 73: "Снег ❄️", 75: "Сильный снегопад ❄️", 77: "Снежные зерна ❄️",
    80: "Ливневый дождь 🌦️", 81: "Сильный ливень ⛈️", 82: "Шквалистый ливень ⛈️",
    85: "Снегопад 🌨️", 86: "Сильная метель ❄️", 95: "Гроза ⚡", 96: "Гроза с градом ⛈️", 99: "Сильная гроза с градом ⛈️"
}


class AICustomizeModal(disnake.ui.Modal):
    """Модальное окно для настройки индивидуального сценария и правил сервера."""
    def __init__(self, cog: "AIChat", panel_view: "AIControlPanelView", current_scenario: str, current_rules: str):
        self.cog = cog
        self.panel_view = panel_view
        components = [
            disnake.ui.TextInput(
                label="Индивидуальный сценарий / стиль общения",
                placeholder="Оставьте пустым для стандартного характера Mirei или напишите свой...",
                custom_id="ai_custom_scenario",
                style=disnake.TextInputStyle.paragraph,
                value=current_scenario[:1000] if current_scenario else "",
                required=False,
                max_length=1000,
            ),
            disnake.ui.TextInput(
                label="Правила сервера для ИИ (пусто = авто-поиск)",
                placeholder="Оставьте пустым, чтобы Mirei сама читала канал #правила, или впишите свои...",
                custom_id="ai_custom_rules",
                style=disnake.TextInputStyle.paragraph,
                value=current_rules[:1000] if current_rules else "",
                required=False,
                max_length=1000,
            ),
        ]
        super().__init__(title="💠 Сценарий и Правила для Mirei", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer()
        scenario = inter.text_values.get("ai_custom_scenario", "").strip()
        rules = inter.text_values.get("ai_custom_rules", "").strip()

        guild_id = inter.guild_id
        self.cog.rules_cache.pop(guild_id, None)

        await self.cog.update_ai_config(
            guild_id,
            aiCustomScenario=scenario or None,
            aiCustomRules=rules or None
        )
        self.cog._clear_channel_memory(inter.channel_id)

        embed = await self.panel_view.build_embed(inter.guild)
        await inter.edit_original_response(embed=embed, view=self.panel_view)


class AIControlPanelView(disnake.ui.View):
    """Единая интерактивная панель управления всеми функциями ИИ (только для администраторов)."""
    def __init__(self, cog: "AIChat", author_id: int, guild_id: int, channel_id: int, current_cfg: Dict[str, Any]):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self._sync_components(current_cfg)

    def _sync_components(self, cfg: Dict[str, Any]):
        is_enabled = cfg.get("aiEnabled", True) is not False
        provider = cfg.get("aiProvider") or "auto"
        chance = int(cfg.get("aiAutoReplyChance") or 0)

        self.toggle_btn.label = "Выключить ИИ" if is_enabled else "Включить ИИ"
        self.toggle_btn.style = disnake.ButtonStyle.danger if is_enabled else disnake.ButtonStyle.success
        self.toggle_btn.emoji = "🔴" if is_enabled else "🟢"

        for opt in self.provider_select.options:
            opt.default = (opt.value == provider)

        for opt in self.chance_select.options:
            opt.default = (int(opt.value) == chance)

    async def build_embed(self, guild: disnake.Guild) -> disnake.Embed:
        cfg = await self.cog.get_ai_config(guild.id)
        self._sync_components(cfg)

        is_enabled = cfg.get("aiEnabled", True) is not False
        provider = cfg.get("aiProvider") or "auto"
        chance = int(cfg.get("aiAutoReplyChance") or 0)
        scenario = cfg.get("aiCustomScenario")
        rules = cfg.get("aiCustomRules")

        status_str = "🟢 **Активен** (Отвечает на упоминания и команды)" if is_enabled else "🔴 **Отключен** (ИИ не отвечает на сервере)"
        model_str = f"**{PROVIDER_NAMES.get(provider, provider)}**"
        chance_str = f"**{CHANCE_LABELS.get(chance, f'{chance}% шанс')}**"
        scenario_str = f"📝 Задан свой: *«{scenario[:120]}{'...' if len(scenario) > 120 else ''}»*" if scenario else "⚪ *По умолчанию (Дружелюбный характер Mirei)*"
        rules_str = f"📝 Заданы вручную (*{len(rules)} симв.*)" if rules else "🔍 *Автоматическое чтение из канала `#правила`*"

        embed = disnake.Embed(
            title="💠 Центр управления ИИ Mirei",
            description=f"Все настройки нейросети для сервера **{guild.name}** сохраняются в базу данных:",
            color=BRAND_COLOR
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="📡 Статус модуля", value=status_str, inline=False)
        embed.add_field(name="🧠 Активная модель", value=model_str, inline=True)
        embed.add_field(name="💬 Живое участие в чате", value=chance_str, inline=True)
        embed.add_field(name="🎬 Индивидуальный сценарий", value=scenario_str, inline=False)
        embed.add_field(name="📜 Знание правил сервера", value=rules_str, inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        return embed

    async def _check_access(self, inter: disnake.MessageInteraction) -> bool:
        await self.cog._ensure_creator_id()
        if not inter.author.guild_permissions.administrator and inter.author.id not in self.cog.creator_ids:
            await inter.response.send_message("⛔ Управлять этой панелью могут только администраторы сервера.", ephemeral=True)
            return False
        return True

    @disnake.ui.select(
        placeholder="🧠 Выберите модель нейросети...",
        row=0,
        options=[
            disnake.SelectOption(label="Авто-выбор (Цепочка всех моделей)", value="auto", emoji="🔄", description="Gemini ➔ ChatGPT ➔ DeepSeek ➔ Mistral"),
            disnake.SelectOption(label="Google Gemini", value="gemini", emoji="✨", description="Быстрая + понимает картинки и мемы"),
            disnake.SelectOption(label="ChatGPT (GPT-4o-mini)", value="chatgpt", emoji="🟢", description="Сбалансированная и умная"),
            disnake.SelectOption(label="DeepSeek V3", value="deepseek", emoji="🐋", description="Живой русский язык и отличная ирония"),
            disnake.SelectOption(label="Mistral AI", value="mistral", emoji="🌪️", description="Отлично держит образ"),
        ]
    )
    async def provider_select(self, select: disnake.ui.Select, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()
        chosen = select.values[0]
        await self.cog.update_ai_config(self.guild_id, aiProvider=chosen)
        embed = await self.build_embed(inter.guild)
        await inter.edit_original_response(embed=embed, view=self)

    @disnake.ui.select(
        placeholder="💬 Настроить шанс участия в обычном чате...",
        row=1,
        options=[
            disnake.SelectOption(label="Выключено (0%)", value="0", emoji="🔇", description="Отвечает только когда её тегнули или сделали Reply"),
            disnake.SelectOption(label="Редко (5%)", value="5", emoji="🌱", description="Иногда комментирует сообщения в чате"),
            disnake.SelectOption(label="Средне (10%)", value="10", emoji="💬", description="Умеренно участвует в живой беседе"),
            disnake.SelectOption(label="Активно (20%)", value="20", emoji="🔥", description="Часто поддерживает разговор в чате"),
            disnake.SelectOption(label="Очень часто (35%)", value="35", emoji="⚡", description="Максимальная активность в беседе"),
        ]
    )
    async def chance_select(self, select: disnake.ui.Select, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()
        chosen_chance = int(select.values[0])
        await self.cog.update_ai_config(self.guild_id, aiAutoReplyChance=chosen_chance)
        embed = await self.build_embed(inter.guild)
        await inter.edit_original_response(embed=embed, view=self)

    @disnake.ui.button(label="Выключить ИИ", style=disnake.ButtonStyle.danger, emoji="🔴", row=2)
    async def toggle_btn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()
        cfg = await self.cog.get_ai_config(self.guild_id)
        new_state = not (cfg.get("aiEnabled", True) is not False)
        await self.cog.update_ai_config(self.guild_id, aiEnabled=new_state)
        embed = await self.build_embed(inter.guild)
        await inter.edit_original_response(embed=embed, view=self)

    @disnake.ui.button(label="Сценарий и Правила", style=disnake.ButtonStyle.secondary, emoji="📝", row=2)
    async def customize_btn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        cfg = await self.cog.get_ai_config(self.guild_id)
        await inter.response.send_modal(
            AICustomizeModal(
                self.cog,
                self,
                cfg.get("aiCustomScenario") or "",
                cfg.get("aiCustomRules") or ""
            )
        )

    @disnake.ui.button(label="Очистить память чата", style=disnake.ButtonStyle.secondary, emoji="♻️", row=2)
    async def reset_memory_btn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        self.cog._clear_channel_memory(inter.channel.id)
        await inter.response.send_message("♻️ Память диалога Mirei в этом канале очищена!", ephemeral=True)


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.gemini_key = (os.getenv("LLM_API_KEY") or "").strip()
        self.openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()

        env_creator = (os.getenv("CREATOR_ID") or "").strip()
        self.creator_ids: set[int] = {int(env_creator)} if env_creator.isdigit() else set()
        self._creator_fetched = False

        self._session: Optional[aiohttp.ClientSession] = None

        # Память контекста канала: channel_id -> deque последних 15 реплик чата
        self.memory: Dict[int, deque] = {}
        self._memory_last_active: Dict[int, float] = {}

        self.cooldowns: Dict[int, float] = {}
        self.cooldown_seconds = 3.0
        self._channel_auto_cooldowns: Dict[int, float] = {}

        self._local_fallback_cfg: Dict[int, Dict[str, Any]] = {}
        self.rules_cache: Dict[int, Tuple[float, str]] = {}
        self._rates_cache: Optional[Tuple[float, str]] = None

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    def _clear_channel_memory(self, channel_id: int):
        self.memory.pop(channel_id, None)
        self._memory_last_active.pop(channel_id, None)

    def _get_channel_history(self, channel_id: int) -> deque:
        """Возвращает историю сообщений канала и очищает неактивные ветки из памяти."""
        now = time.time()
        last_ts = self._memory_last_active.get(channel_id, 0.0)
        if last_ts and (now - last_ts) > MEMORY_TTL_SECONDS:
            self._clear_channel_memory(channel_id)

        if len(self.memory) > MAX_MEMORY_CHANNELS:
            expired = [cid for cid, ts in self._memory_last_active.items() if (now - ts) > MEMORY_TTL_SECONDS]
            for cid in expired:
                self._clear_channel_memory(cid)
            if len(self.memory) > MAX_MEMORY_CHANNELS:
                oldest = sorted(self._memory_last_active.items(), key=lambda x: x[1])[: len(self.memory) // 5]
                for cid, _ in oldest:
                    self._clear_channel_memory(cid)

        self._memory_last_active[channel_id] = now
        return self.memory.setdefault(channel_id, deque(maxlen=15))

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(family=socket.AF_INET, limit=50, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=25)
            )
        return self._session

    # -------------------------------------------------------------------------
    # ЧТЕНИЕ И СОХРАНЕНИЕ НАСТРОЕК ИИ В МОДУЛЬНУЮ БД C#
    # -------------------------------------------------------------------------
    async def get_ai_config(self, guild_id: int) -> Dict[str, Any]:
        db_cfg = await api.get_guild_config(str(guild_id)) or {}
        ai_sub = db_cfg.get("ai") or {}
        sec_sub = db_cfg.get("security") or {}
        local_cfg = self._local_fallback_cfg.get(guild_id, {})

        return {
            "aiEnabled": ai_sub.get("enabled") if "enabled" in ai_sub else local_cfg.get("aiEnabled", True),
            "aiProvider": ai_sub.get("provider") or local_cfg.get("aiProvider", "auto"),
            "aiAutoReplyChance": ai_sub.get("autoReplyChance") if "autoReplyChance" in ai_sub else local_cfg.get("aiAutoReplyChance", 0),
            "aiCustomScenario": ai_sub.get("customScenario") if "customScenario" in ai_sub else local_cfg.get("aiCustomScenario"),
            "aiCustomRules": ai_sub.get("customRules") if "customRules" in ai_sub else local_cfg.get("aiCustomRules"),
            "logChannelId": db_cfg.get("logChannelId"),
            "verificationRoleId": sec_sub.get("verificationRoleId"),
            "trapChannelId": sec_sub.get("trapChannelId"),
        }

    async def update_ai_config(self, guild_id: int, **kwargs) -> bool:
        current = await self.get_ai_config(guild_id)
        current.update(kwargs)
        if len(self._local_fallback_cfg) > MAX_RULES_CACHE_GUILDS:
            self._local_fallback_cfg.clear()
        self._local_fallback_cfg[guild_id] = current

        ai_payload = {
            "enabled": current.get("aiEnabled", True),
            "provider": current.get("aiProvider") or "auto",
            "autoReplyChance": int(current.get("aiAutoReplyChance") or 0),
            "customScenario": current.get("aiCustomScenario"),
            "customRules": current.get("aiCustomRules"),
        }
        return await api.update_ai_config(str(guild_id), ai_payload)

    # -------------------------------------------------------------------------
    # РАСПОЗНАВАНИЕ СОЗДАТЕЛЯ (DISU) ПО DISCORD ID
    # -------------------------------------------------------------------------
    async def _ensure_creator_id(self):
        if self._creator_fetched:
            return
        self._creator_fetched = True
        try:
            app_info = await self.bot.application_info()
            if app_info.owner:
                self.creator_ids.add(app_info.owner.id)
            if app_info.team:
                for member in app_info.team.members:
                    self.creator_ids.add(member.id)
        except Exception:
            pass

    async def _get_author_identity_tag(self, author: disnake.abc.User, guild: Optional[disnake.Guild]) -> str:
        await self._ensure_creator_id()

        is_creator = (
            author.id in self.creator_ids
            or author.name.lower() in ("disu", "disuepic")
        )
        is_guild_owner = bool(guild and author.id == guild.owner_id)

        if is_creator and is_guild_owner:
            return (
                f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой СОЗДАТЕЛЬ Disu (ID: {author.id}), он же владелец этого сервера. "
                f"Ник здесь: «{author.display_name}».]"
            )
        if is_creator:
            return (
                f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой СОЗДАТЕЛЬ Disu (ID: {author.id}) под ником «{author.display_name}».]"
            )
        if "disu" in author.display_name.lower():
            return (
                f"⚠️ [ВНИМАНИЕ: У автора ник «{author.display_name}», но его ID ({author.id}) НЕ совпадает с Disu!]"
            )
        if is_guild_owner:
            return (
                f"👑 [СИСТЕМНАЯ МЕТКА: Пишет владелец этого сервера «{author.display_name}» (глобальный создатель — Disu).]"
            )
        return ""

    # -------------------------------------------------------------------------
    # УМНЫЕ ДЕЙСТВИЯ МОДЕРАЦИИ (ВАРИАНТ Б: ПРОВЕРКА ПРАВ И ИЕРАРХИИ)
    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_action_params(raw_params: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for part in raw_params.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip().lower()] = v.strip()
        return result

    def _can_moderate_target(self, guild: disnake.Guild, actor: disnake.Member, target: disnake.Member) -> Optional[str]:
        if target.id == actor.id:
            return "нельзя применить действие к самому себе"
        if target.id == self.bot.user.id:
            return "нельзя применить действие ко мне"
        if target.id == guild.owner_id:
            return "нельзя наказать владельца сервера"
        if actor.id != guild.owner_id and actor.id not in self.creator_ids and target.top_role >= actor.top_role:
            return "роль этого участника равна или выше твоей"
        if guild.me and target.top_role >= guild.me.top_role:
            return "роль этого участника выше моей роли в настройках сервера"
        return None

    async def _execute_ai_action(self, message: disnake.Message, raw_action: str) -> str:
        """Разбирает и безопасно выполняет команду модерации от имени Mirei."""
        if not message.guild or not isinstance(message.author, disnake.Member):
            return "⚠️ Действия модерации доступны только на сервере."

        guild = message.guild
        actor = message.author
        is_trusted_boss = (actor.id == guild.owner_id) or (actor.id in self.creator_ids)

        parts = [p.strip() for p in raw_action.split("|")]
        action_name = parts[0].lower() if parts else ""
        params = self._parse_action_params("|".join(parts[1:]))

        def extract_user_id() -> Optional[int]:
            raw_uid = re.sub(r"\D", "", params.get("user_id", ""))
            if raw_uid.isdigit():
                return int(raw_uid)
            # Если в ответе есть упоминание другого пользователя (не бота), берём его
            for m in message.mentions:
                if m.id != self.bot.user.id:
                    return m.id
            return None

        # 1. TIMEOUT (МУТ)
        if action_name == "timeout":
            if not (is_trusted_boss or actor.guild_permissions.moderate_members):
                return "⛔ У тебя нет прав на таймаут участников."
            uid = extract_user_id()
            target = guild.get_member(uid) if uid else None
            if not target:
                return "⚠️ Не удалось найти этого участника на сервере."
            if err := self._can_moderate_target(guild, actor, target):
                return f"⛔ Не могу выполнить: {err}."

            try:
                mins = max(1, min(40320, int(re.sub(r"\D", "", params.get("minutes", "10")) or "10")))
            except ValueError:
                mins = 10
            reason = (params.get("reason") or "По запросу в чате через Mirei")[:200]

            try:
                await target.timeout(duration=datetime.timedelta(minutes=mins), reason=f"{reason} (ИИ-команда от {actor})")
                log_embed = disnake.Embed(
                    title="🔇 Применен таймаут (через ИИ Mirei)",
                    description=f"**Нарушитель:** {target.mention} (`{target.id}`)\n**Модератор:** {actor.mention}\n**Время:** {mins} мин.\n**Причина:** {reason}",
                    color=ACCENT_GOLD,
                    timestamp=disnake.utils.utcnow()
                )
                log_embed.set_footer(text=UNIFIED_FOOTER)
                await send_log(guild, log_embed)
                return f"✅ Готово! {target.mention} отправлен в таймаут на **{mins} мин.** *(Причина: {reason})*"
            except disnake.Forbidden:
                return "⚠️ У меня не хватает прав Discord для выдачи таймаута."

        # 2. KICK (КИК)
        if action_name == "kick":
            if not (is_trusted_boss or actor.guild_permissions.kick_members):
                return "⛔ У тебя нет прав на исключение участников."
            uid = extract_user_id()
            target = guild.get_member(uid) if uid else None
            if not target:
                return "⚠️ Участник не найден на сервере."
            if err := self._can_moderate_target(guild, actor, target):
                return f"⛔ Не могу выполнить: {err}."

            reason = (params.get("reason") or "Исключен через Mirei")[:200]
            try:
                await target.kick(reason=f"{reason} (ИИ-команда от {actor})")
                log_embed = disnake.Embed(
                    title="👢 Участник исключен (через ИИ Mirei)",
                    description=f"**Исключен:** {target.mention} (`{target.id}`)\n**Модератор:** {actor.mention}\n**Причина:** {reason}",
                    color=COMBAT_RED,
                    timestamp=disnake.utils.utcnow()
                )
                log_embed.set_footer(text=UNIFIED_FOOTER)
                await send_log(guild, log_embed)
                return f"👢 Участник **{target.display_name}** исключен с сервера. *(Причина: {reason})*"
            except disnake.Forbidden:
                return "⚠️ У меня недостаточно прав для кика этого участника."

        # 3. BAN (БАН)
        if action_name == "ban":
            if not (is_trusted_boss or actor.guild_permissions.ban_members):
                return "⛔ У тебя нет прав на блокировку участников."
            uid = extract_user_id()
            target = guild.get_member(uid) if uid else None
            if not target:
                return "⚠️ Участник не найден на сервере."
            if err := self._can_moderate_target(guild, actor, target):
                return f"⛔ Не могу выполнить: {err}."

            reason = (params.get("reason") or "Заблокирован через Mirei")[:200]
            try:
                await target.ban(reason=f"{reason} (ИИ-команда от {actor})", clean_history_duration=86400)
                log_embed = disnake.Embed(
                    title="🔨 Участник заблокирован (через ИИ Mirei)",
                    description=f"**Забанен:** {target.mention} (`{target.id}`)\n**Модератор:** {actor.mention}\n**Причина:** {reason}",
                    color=COMBAT_RED,
                    timestamp=disnake.utils.utcnow()
                )
                log_embed.set_footer(text=UNIFIED_FOOTER)
                await send_log(guild, log_embed)
                return f"🔨 Участник **{target.display_name}** заблокирован на сервере. *(Причина: {reason})*"
            except disnake.Forbidden:
                return "⚠️ У меня недостаточно прав для бана этого участника."

        # 4. CLEAR (ОЧИСТКА ЧАТА)
        if action_name == "clear":
            if not (is_trusted_boss or actor.guild_permissions.manage_messages):
                return "⛔ У тебя нет прав на удаление сообщений."
            try:
                amount = max(1, min(100, int(re.sub(r"\D", "", params.get("amount", "10")) or "10")))
            except ValueError:
                amount = 10

            cutoff = disnake.utils.utcnow() - datetime.timedelta(days=14)
            try:
                deleted = await message.channel.purge(limit=amount + 1, after=cutoff)
                count = max(0, len(deleted) - 1)
                return f"🧹 Очистила последние **{count}** сообщений в этом канале!"
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на удаление сообщений в этом канале."

        # 5. LOCK / UNLOCK (БЛОКИРОВКА КАНАЛА)
        if action_name in ("lock", "unlock"):
            if not (is_trusted_boss or actor.guild_permissions.manage_channels):
                return "⛔ У тебя нет прав на управление каналами."
            cfg = await api.get_guild_config(str(guild.id)) or {}
            role_id = (cfg.get("security") or {}).get("verificationRoleId")
            target_role = (guild.get_role(int(role_id)) if (role_id and str(role_id).isdigit()) else None) or guild.default_role

            is_lock = action_name == "lock"
            try:
                await message.channel.set_permissions(
                    target_role,
                    send_messages=False if is_lock else None,
                    reason=f"ИИ-команда ({action_name}) от {actor}"
                )
                return "🔒 Канал закрыт для сообщений." if is_lock else "🔓 Канал снова открыт для общения!"
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на изменение разрешений этого канала."

        # 6. SLOWMODE (МЕДЛЕННЫЙ РЕЖИМ)
        if action_name == "slowmode":
            if not (is_trusted_boss or actor.guild_permissions.manage_channels):
                return "⛔ У тебя нет прав на управление каналами."
            try:
                sec = max(0, min(21600, int(re.sub(r"\D", "", params.get("seconds", "0")) or "0")))
            except ValueError:
                sec = 0
            try:
                await message.channel.edit(slowmode_delay=sec)
                return "⚡ Медленный режим отключён." if sec == 0 else f"⏳ Медленный режим включён: **1 сообщение в {sec} сек.**"
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на изменение настроек канала."

        return ""

    # -------------------------------------------------------------------------
    # ЧТЕНИЕ EMBED-СООБЩЕНИЙ И КАРТИНОК
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_embeds_text(embeds: List[disnake.Embed]) -> str:
        if not embeds:
            return ""
        parts = []
        for idx, emb in enumerate(embeds[:3], 1):
            items = []
            if emb.author and emb.author.name:
                items.append(f"Автор: {emb.author.name}")
            if emb.title:
                items.append(f"Заголовок: {emb.title}")
            if emb.description:
                items.append(f"Текст: {emb.description[:1500]}")
            for f in emb.fields[:10]:
                items.append(f"{f.name}: {f.value[:350]}")
            if emb.footer and emb.footer.text:
                items.append(f"Подвал: {emb.footer.text}")
            if items:
                parts.append(f"[Вложение Embed #{idx} -> " + " | ".join(items) + "]")
        return "\n".join(parts)

    @staticmethod
    def _extract_embed_image_url(embeds: List[disnake.Embed]) -> Optional[str]:
        for emb in embeds:
            if emb.image and emb.image.url:
                return emb.image.url
            if emb.thumbnail and emb.thumbnail.url:
                return emb.thumbnail.url
        return None

    async def _download_image_base64(
        self,
        attachment: Optional[disnake.Attachment] = None,
        image_url: Optional[str] = None
    ) -> Optional[Tuple[str, str]]:
        target_url = None
        expected_type = None

        if attachment:
            content_type = (attachment.content_type or "").split(";")[0].strip().lower()
            if content_type in ALLOWED_IMAGE_TYPES and attachment.size <= 4 * 1024 * 1024:
                target_url = attachment.url
                expected_type = content_type
        elif image_url:
            target_url = image_url

        if not target_url:
            return None

        try:
            session = await self._get_session()
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    ct = expected_type or (resp.headers.get("Content-Type", "").split(";")[0].strip().lower())
                    if ct not in ALLOWED_IMAGE_TYPES:
                        ct = "image/png"
                    raw_bytes = await resp.read()
                    if len(raw_bytes) > 4 * 1024 * 1024:
                        return None
                    return ct, base64.b64encode(raw_bytes).decode("utf-8")
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    # СБОР ЗНАНИЙ О СЕРВЕРЕ (ТОЛЬКО ПУБЛИЧНЫЕ КАНАЛЫ БЕЗ СЧЕТЧИКОВ И АДМИНКИ)
    # -------------------------------------------------------------------------
    async def _get_server_rules_text(self, guild: disnake.Guild, cfg: Dict[str, Any]) -> str:
        custom = cfg.get("aiCustomRules")
        if custom:
            return custom

        now = time.time()
        cached = self.rules_cache.get(guild.id)
        if cached and (now - cached[0]) < 1800:
            return cached[1]

        if len(self.rules_cache) > MAX_RULES_CACHE_GUILDS:
            expired = [gid for gid, (ts, _) in self.rules_cache.items() if (now - ts) >= 1800]
            for gid in expired:
                self.rules_cache.pop(gid, None)

        rules_channel: Optional[disnake.TextChannel] = guild.rules_channel
        if not rules_channel:
            for ch in guild.text_channels:
                name_low = ch.name.lower()
                if any(k in name_low for k in ("правил", "rules", "устав")):
                    rules_channel = ch
                    break

        if not rules_channel:
            self.rules_cache[guild.id] = (now, "Специальный канал правил не найден, действуют общие нормы адекватности.")
            return self.rules_cache[guild.id][1]

        collected = []
        try:
            async for msg in rules_channel.history(limit=8, oldest_first=True):
                if msg.content:
                    collected.append(msg.content[:2000])
                if msg.embeds:
                    collected.append(self._extract_embeds_text(msg.embeds))
        except disnake.HTTPException:
            pass

        rules_text = "\n".join(collected)[:4000] if collected else f"Правила находятся в канале {rules_channel.mention}."
        self.rules_cache[guild.id] = (now, rules_text)
        return rules_text

    @staticmethod
    def _get_public_channels(guild: disnake.Guild, cfg: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        staff_keywords = (
            "админ", "адмен", "admin", "модер", "moder", "staff", "стафф",
            "логи", "logs", "audit", "аудит", "тикет", "ticket", "бан-лист", "руководств"
        )
        counter_keywords = (
            "all members", "members:", "bots:", "online:",
            "участников:", "онлайн:", "ботов:", "статистик", "stats"
        )
        log_ch_id = str(cfg.get("logChannelId") or "")

        verify_role: Optional[disnake.Role] = None
        v_role_id = cfg.get("verificationRoleId")
        if v_role_id and str(v_role_id).isdigit():
            verify_role = guild.get_role(int(v_role_id))

        if not verify_role:
            for r in guild.roles:
                if not r.is_default() and not r.managed and any(
                    w in r.name.lower() for w in ("участник", "member", "verif", "игрок", "user")
                ):
                    verify_role = r
                    break

        check_roles = [guild.default_role]
        if verify_role:
            check_roles.append(verify_role)

        def is_staff_or_hidden_name(ch: disnake.abc.GuildChannel) -> bool:
            if str(ch.id) == log_ch_id:
                return True
            ch_name = ch.name.lower()
            cat_name = ch.category.name.lower() if ch.category else ""
            return any(k in ch_name or k in cat_name for k in staff_keywords)

        text_ch_list: List[str] = []
        for ch in guild.text_channels:
            if is_staff_or_hidden_name(ch):
                continue

            if any(ch.permissions_for(r).view_channel for r in check_roles):
                topic_str = f" ({ch.topic[:50]})" if ch.topic else ""
                nsfw_tag = " [18+ NSFW]" if ch.is_nsfw() else ""
                text_ch_list.append(f"<#{ch.id}> (#{ch.name}{nsfw_tag}{topic_str})")

        voice_ch_list: List[str] = []
        for vc in guild.voice_channels:
            if is_staff_or_hidden_name(vc):
                continue

            vc_low = vc.name.lower()
            if any(k in vc_low for k in counter_keywords) or re.search(r"[:—\-]\s*\d+\s*$", vc.name):
                continue

            is_afk = (vc == guild.afk_channel)
            active_role = verify_role if verify_role else guild.default_role
            perms = vc.permissions_for(active_role)

            if perms.view_channel and (perms.connect or is_afk):
                voice_ch_list.append(f"<#{vc.id}> (🔊 {vc.name})")

        return text_ch_list, voice_ch_list

    async def _build_guild_knowledge(
        self,
        guild: Optional[disnake.Guild],
        current_channel: disnake.abc.Messageable,
        cfg: Dict[str, Any]
    ) -> str:
        if not guild:
            return "Диалог идет в личных сообщениях (DM). Твой создатель — Disu."

        owner_str = f"<@{guild.owner_id}>"
        if guild.owner:
            owner_str = f"{guild.owner.display_name} (<@{guild.owner.id}>)"

        text_ch_list, voice_ch_list = self._get_public_channels(guild, cfg)

        text_summary = ", ".join(text_ch_list[:25]) if text_ch_list else "Нет доступных"
        voice_summary = ", ".join(voice_ch_list[:15]) if voice_ch_list else "Голосовые каналы отсутствуют"

        rules_text = await self._get_server_rules_text(guild, cfg)
        curr_ch_name = getattr(current_channel, "name", "ЛС")

        return (
            f"\n--- ИНФОРМАЦИЯ О СЕРВЕРЕ ---\n"
            f"• Сервер: «{guild.name}» (Участников: {guild.member_count})\n"
            f"• Создатель бота: Disu | Владелец сервера: {owner_str}\n"
            f"• Текущий канал: <#{getattr(current_channel, 'id', 0)}> (#{curr_ch_name})\n"
            f"• Текстовые каналы: {text_summary}\n"
            f"• Голосовые каналы: {voice_summary}\n"
            f"• Правила:\n{rules_text}\n"
            f"----------------------------"
        )

    # -------------------------------------------------------------------------
    # ВЫХОД В ИНТЕРНЕТ (ПОГОДА, ВАЛЮТЫ/КРИПТА, GOOGLE NEWS & WIKIPEDIA)
    # -------------------------------------------------------------------------
    async def _fetch_weather(self, text: str) -> Optional[str]:
        clean = re.sub(
            r"(какая|какой|сейчас|сегодня|завтра|загугли|найди|скажи|покажи|погода|погоду|градусов|температура|в|во|на)\b",
            " ",
            text,
            flags=re.IGNORECASE
        )
        clean = re.sub(r"[^\w\s\-]", "", clean).strip()
        city_query = " ".join(clean.split()[:3]).strip()
        if len(city_query) < 2:
            city_query = "Москва"

        session = await self._get_session()
        headers = {"User-Agent": "MireiDiscordBot/2.0"}
        lat, lon, place_name = None, None, city_query

        try:
            nom_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city_query)}&format=json&limit=1&accept-language=ru"
            async with session.get(nom_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    nom_data = await resp.json()
                    if nom_data:
                        lat = float(nom_data[0]["lat"])
                        lon = float(nom_data[0]["lon"])
                        place_name = nom_data[0].get("display_name", city_query).split(",")[0]
        except Exception:
            pass

        if lat is None or lon is None:
            candidates = [city_query]
            if len(city_query) > 4:
                candidates.extend([city_query[:-1], city_query[:-1] + "а", city_query[:-1] + "я"])
            for cand in candidates:
                try:
                    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(cand)}&count=1&language=ru"
                    async with session.get(geo_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            gdata = await resp.json()
                            results = gdata.get("results")
                            if results:
                                lat = results[0]["latitude"]
                                lon = results[0]["longitude"]
                                place_name = results[0].get("name", cand)
                                break
                except Exception:
                    continue

        if lat is None or lon is None:
            return None

        try:
            w_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code&timezone=auto"
            )
            async with session.get(w_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    wdata = await resp.json()
                    cur = wdata.get("current", {})
                    temp = cur.get("temperature_2m")
                    feels = cur.get("apparent_temperature")
                    hum = cur.get("relative_humidity_2m")
                    wind = cur.get("wind_speed_10m")
                    code = cur.get("weather_code", 0)
                    desc = WMO_WEATHER_CODES.get(code, "Переменная облачность")
                    return (
                        f"Погода в г. {place_name} прямо сейчас: {desc}, температура {temp}°C "
                        f"(ощущается как {feels}°C), ветер {wind} км/ч, влажность {hum}%."
                    )
        except Exception:
            pass
        return None

    async def _fetch_currency_rates(self) -> Optional[str]:
        now = time.time()
        if self._rates_cache and (now - self._rates_cache[0]) < RATES_CACHE_TTL_SECONDS:
            return self._rates_cache[1]

        session = await self._get_session()

        async def get_cbr() -> Optional[str]:
            try:
                async with session.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        raw = await resp.text()
                        data = json.loads(raw)
                        val = data.get("Valute", {})
                        usd = val.get("USD", {}).get("Value")
                        eur = val.get("EUR", {}).get("Value")
                        cny = val.get("CNY", {}).get("Value")
                        kzt = val.get("KZT", {}).get("Value")
                        if usd and eur:
                            return (
                                f"Официальный курс ЦБ РФ: 1 USD (доллар) = {usd:.2f} руб., "
                                f"1 EUR (евро) = {eur:.2f} руб., 1 CNY (юань) = {cny:.2f} руб., 100 KZT (тенге) = {kzt:.2f} руб."
                            )
            except Exception:
                pass
            return None

        async def get_crypto() -> Optional[str]:
            try:
                cg_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network&vs_currencies=usd,rub"
                async with session.get(cg_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        cg = await resp.json()
                        btc_usd = cg.get("bitcoin", {}).get("usd")
                        ton_usd = cg.get("the-open-network", {}).get("usd")
                        ton_rub = cg.get("the-open-network", {}).get("rub")
                        if btc_usd:
                            return f"Курс крипты: Bitcoin (BTC) = ${btc_usd:,}, TON = ${ton_usd} ({ton_rub} руб.)."
            except Exception:
                pass
            return None

        cbr_res, crypto_res = await asyncio.gather(get_cbr(), get_crypto())
        lines = [line for line in (cbr_res, crypto_res) if line]

        if lines:
            result = "\n".join(lines)
            self._rates_cache = (now, result)
            return result
        return None

    async def _fetch_web_search(self, query: str) -> Optional[str]:
        clean_q = re.sub(
            r"\b(загугли|найди в интернете|найди в инете|найди|поищи|расскажи про|что такое|кто такой)\b",
            "",
            query,
            flags=re.IGNORECASE
        ).strip()
        if len(clean_q) < 2:
            clean_q = query

        session = await self._get_session()

        async def search_news() -> List[str]:
            items_out = []
            try:
                g_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_q[:120])}&hl=ru&gl=RU&ceid=RU:ru"
                async with session.get(g_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        xml_text = await resp.text()
                        items = re.findall(r"<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>.*?</item>", xml_text, flags=re.DOTALL)
                        for title, pub_date in items[:4]:
                            clean_title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
                            items_out.append(f"• Новость ({pub_date[:16]}): {clean_title}")
            except Exception:
                pass
            return items_out

        async def search_wiki() -> List[str]:
            items_out = []
            try:
                w_url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q[:120])}&utf8=&format=json&srlimit=3"
                headers = {"User-Agent": "MireiDiscordBot/2.0"}
                async with session.get(w_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        wdata = await resp.json()
                        for item in wdata.get("query", {}).get("search", [])[:3]:
                            t = item.get("title", "")
                            snip = html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", ""))).strip()
                            if snip:
                                items_out.append(f"• Справка ({t}): {snip}")
            except Exception:
                pass
            return items_out

        news_res, wiki_res = await asyncio.gather(search_news(), search_wiki())
        results = news_res + wiki_res
        return "\n".join(results) if results else None

    async def _gather_internet_context(self, user_text: str) -> str:
        low = user_text.lower()
        blocks = []

        if any(w in low for w in ("погод", "градус", "температур", "дождь в", "снег в", "метео")):
            weather_info = await self._fetch_weather(user_text)
            if weather_info:
                blocks.append(weather_info)

        if any(w in low for w in ("курс", "доллар", "евро", "рубл", "юан", "тенге", "биткоин", "btc", "крипт", "ton ")):
            rates_info = await self._fetch_currency_rates()
            if rates_info:
                blocks.append(rates_info)

        search_triggers = (
            "загугли", "найди", "поищи", "новости", "когда выйдет", "когда вышел",
            "кто выиграл", "что случилось", "кто такой", "что такое", "актуальн", "в 2025", "в 2026"
        )
        if any(w in low for w in search_triggers) and not blocks:
            web_info = await self._fetch_web_search(user_text)
            if web_info:
                blocks.append(web_info)

        if not blocks:
            return ""

        joined = "\n".join(blocks)
        return (
            f"\n\n[ДАННЫЕ ИЗ ИНТЕРНЕТА В РЕАЛЬНОМ ВРЕМЕНИ]:\n"
            f"{joined}\n"
            f"(Используй эти свежие данные для ответа пользователю!)"
        )

    # -------------------------------------------------------------------------
    # БАЗОВЫЙ ТРАНСПОРТ ДЛЯ OPENAI-СОВМЕСТИМЫХ МОДЕЛЕЙ
    # -------------------------------------------------------------------------
    async def _request_openai_endpoint(
        self,
        url: str,
        api_key: Optional[str],
        models: List[str],
        system_prompt: str,
        history: deque,
        current_msg: str,
        image_data: Optional[Tuple[str, str]] = None
    ) -> Optional[str]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        if image_data:
            mime_type, b64_str = image_data
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": current_msg},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_str}"}}
                ]
            })
        else:
            messages.append({"role": "user", "content": current_msg})

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        session = await self._get_session()
        for model_name in models:
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 1500,
            }
            try:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=22)) as resp:
                    if resp.status == 200:
                        raw_text = (await resp.text()).strip()
                        if not raw_text:
                            continue
                        try:
                            data = json.loads(raw_text)
                            choices = data.get("choices") or []
                            if choices:
                                reply = (choices[0].get("message", {}).get("content") or "").strip()
                                if reply:
                                    return reply
                        except json.JSONDecodeError:
                            if not raw_text.startswith("<!DOCTYPE") and not raw_text.startswith("<html"):
                                return raw_text
                    else:
                        err = await resp.text()
                        log.warning("Модель %s (%s) вернула %s: %s", model_name, url, resp.status, err[:120])
            except Exception as e:
                log.warning("Ошибка вызова модели %s (%s): %s", model_name, url, e)
                continue
        return None

    # =========================================================================
    # МЕТОДЫ МОДЕЛЕЙ (GEMINI, CHATGPT, DEEPSEEK, MISTRAL)
    # =========================================================================

    async def _call_gemini(
        self,
        system_prompt: str,
        history: deque,
        current_msg: str,
        image_data: Optional[Tuple[str, str]]
    ) -> Optional[str]:
        if not self.gemini_key:
            return None

        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        user_parts: List[dict] = [{"text": current_msg}]
        if image_data:
            mime_type, b64_str = image_data
            user_parts.append({"inlineData": {"mimeType": mime_type, "data": b64_str}})

        contents.append({"role": "user", "parts": user_parts})

        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "safetySettings": SAFETY_SETTINGS_MODERATE,
            "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2048},
        }

        session = await self._get_session()
        for model_name in GEMINI_MODELS_LIST:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates") or []
                        if not candidates:
                            return "🛡️ Фильтр безопасности заблокировал этот запрос — попробуй сформулировать помягче."
                        parts = candidates[0].get("content", {}).get("parts", [])
                        reply = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought")).strip()
                        if not reply and parts:
                            reply = parts[-1].get("text", "").strip()
                        if reply:
                            return reply
                    elif resp.status in (429, 500, 503):
                        continue
            except Exception:
                continue
        return None

    async def _call_chatgpt(
        self,
        system_prompt: str,
        history: deque,
        current_msg: str,
        image_data: Optional[Tuple[str, str]]
    ) -> Optional[str]:
        if self.openai_key:
            res = await self._request_openai_endpoint(
                "https://api.openai.com/v1/chat/completions",
                self.openai_key,
                ["gpt-4o-mini"],
                system_prompt, history, current_msg, image_data
            )
            if res:
                return res

        res = await self._request_openai_endpoint(
            "https://api.llm7.io/v1/chat/completions",
            "unused",
            ["gpt-4o-mini", "default"],
            system_prompt, history, current_msg, image_data
        )
        if res:
            return res

        return await self._request_openai_endpoint(
            "https://text.pollinations.ai/openai",
            None,
            ["openai", "openai-fast"],
            system_prompt, history, current_msg, image_data
        )

    async def _call_deepseek(
        self,
        system_prompt: str,
        history: deque,
        current_msg: str
    ) -> Optional[str]:
        if self.openrouter_key:
            res = await self._request_openai_endpoint(
                "https://openrouter.ai/api/v1/chat/completions",
                self.openrouter_key,
                ["deepseek/deepseek-chat:free"],
                system_prompt, history, current_msg
            )
            if res:
                return res

        res = await self._request_openai_endpoint(
            "https://text.pollinations.ai/openai",
            None,
            ["deepseek"],
            system_prompt, history, current_msg
        )
        if res:
            return res

        return await self._request_openai_endpoint(
            "https://api.llm7.io/v1/chat/completions",
            "unused",
            ["deepseek-v3", "default"],
            system_prompt, history, current_msg
        )

    async def _call_mistral(
        self,
        system_prompt: str,
        history: deque,
        current_msg: str
    ) -> Optional[str]:
        res = await self._request_openai_endpoint(
            "https://text.pollinations.ai/openai",
            None,
            ["mistral"],
            system_prompt, history, current_msg
        )
        if res:
            return res

        return await self._request_openai_endpoint(
            "https://api.llm7.io/v1/chat/completions",
            "unused",
            ["mistral-small", "default"],
            system_prompt, history, current_msg
        )

    # -------------------------------------------------------------------------
    # ГЛАВНЫЙ МАРШРУТИЗАТОР ЗАПРОСОВ К ИИ
    # -------------------------------------------------------------------------
    async def _ask_llm(
        self,
        guild: Optional[disnake.Guild],
        channel: disnake.abc.Messageable,
        author: disnake.abc.User,
        user_text: str,
        image_data: Optional[Tuple[str, str]] = None,
        is_spontaneous: bool = False
    ) -> Optional[str]:
        guild_id = guild.id if guild else 0
        channel_id = getattr(channel, "id", 0)
        history = self._get_channel_history(channel_id)

        cfg = await self.get_ai_config(guild_id) if guild else {}
        base_prompt = PROMPT_CHARACTER_BASE

        custom_scenario = cfg.get("aiCustomScenario")
        if custom_scenario:
            base_prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ СЦЕНАРИЙ ЭТОГО СЕРВЕРА:\n{custom_scenario}"

        if is_spontaneous:
            base_prompt += (
                "\n\n[КОНТЕКСТ: Тебя сейчас не тегали напрямую, ты сама решила по-дружески поддержать текущую беседу в чате. "
                "Ответь коротко, в тему разговора (1–2 предложения) и НЕ выполняй никаких тегов ACTION.]"
            )

        guild_knowledge = await self._build_guild_knowledge(guild, channel, cfg)
        identity_tag = await self._get_author_identity_tag(author, guild)

        msk_tz = datetime.timezone(datetime.timedelta(hours=3))
        now_msk = datetime.datetime.now(msk_tz)
        weekday_name = WEEKDAYS_RU[now_msk.weekday()]
        time_info = now_msk.strftime(f"{weekday_name}, %d.%m.%Y, %H:%M (МСК)")

        internet_context = "" if is_spontaneous else await self._gather_internet_context(user_text)

        active_prompt = (
            f"{base_prompt}\n"
            f"{guild_knowledge}\n"
            f"Текущее время и дата: {time_info}."
            f"{internet_context}"
        )

        author_header = f"{author.display_name} (ID: {author.id})"
        current_msg = f"{identity_tag}\n{author_header}: {user_text}".strip() if identity_tag else f"{author_header}: {user_text}"

        preferred = cfg.get("aiProvider") or "auto"
        reply: Optional[str] = None

        if preferred == "gemini":
            reply = await self._call_gemini(active_prompt, history, current_msg, image_data)
        elif preferred == "chatgpt":
            reply = await self._call_chatgpt(active_prompt, history, current_msg, image_data)
        elif preferred == "deepseek":
            reply = await self._call_deepseek(active_prompt, history, current_msg)
        elif preferred == "mistral":
            reply = await self._call_mistral(active_prompt, history, current_msg)

        if not reply:
            reply = await self._call_gemini(active_prompt, history, current_msg, image_data)
        if not reply:
            reply = await self._call_chatgpt(active_prompt, history, current_msg, image_data)
        if not reply and not image_data:
            reply = await self._call_deepseek(active_prompt, history, current_msg)
        if not reply and not image_data:
            reply = await self._call_mistral(active_prompt, history, current_msg)

        if reply:
            history_text = f"{author.display_name}: {user_text} [Изображение]" if image_data else f"{author.display_name}: {user_text}"
            history.append({"role": "user", "content": history_text})
            history.append({"role": "assistant", "content": reply})
            self._memory_last_active[channel_id] = time.time()
            return reply

        return None

    # -------------------------------------------------------------------------
    # ОБРАБОТКА СООБЩЕНИЙ И КОНТЕКСТА ЧАТА
    # -------------------------------------------------------------------------
    @staticmethod
    def _is_ignored_chat_channel(channel: disnake.abc.GuildChannel, guild: disnake.Guild) -> bool:
        if guild.rules_channel and channel.id == guild.rules_channel.id:
            return True
        name_low = getattr(channel, "name", "").lower()
        ignored_words = ("правил", "rules", "логи", "logs", "audit", "аудит", "админ", "admin", "модер", "moder", "тикет", "ticket")
        return any(w in name_low for w in ignored_words)

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot:
            return

        is_dm = message.guild is None
        ref_msg: Optional[disnake.Message] = None

        if message.reference and message.reference.message_id:
            ref_msg = message.reference.resolved if isinstance(message.reference.resolved, disnake.Message) else None
            if ref_msg is None:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                except disnake.HTTPException:
                    ref_msg = None

        is_spontaneous = False
        now = time.time()

        if not is_dm:
            cfg = await self.get_ai_config(message.guild.id)
            if cfg.get("trapChannelId") and str(message.channel.id) == str(cfg["trapChannelId"]):
                return
            if cfg.get("aiEnabled", True) is False:
                return

            is_mentioned = self.bot.user in message.mentions
            is_reply_to_bot = bool(ref_msg and ref_msg.author.id == self.bot.user.id)

            if not (is_mentioned or is_reply_to_bot):
                # Запоминаем реплику в контексте канала, чтобы Mirei знала, о чём говорят в чате
                if message.content and not message.content.startswith(("/", "!", ".")) and not self._is_ignored_chat_channel(message.channel, message.guild):
                    history = self._get_channel_history(message.channel.id)
                    history.append({"role": "user", "content": f"{message.author.display_name}: {message.content[:400]}"})

                    chance = int(cfg.get("aiAutoReplyChance") or 0)
                    last_auto = self._channel_auto_cooldowns.get(message.channel.id, 0.0)
                    if (
                        chance > 0
                        and len(message.content.strip()) >= 8
                        and (now - last_auto) >= AUTO_REPLY_CHANNEL_COOLDOWN
                        and random.randint(1, 100) <= chance
                    ):
                        is_spontaneous = True
                        self._channel_auto_cooldowns[message.channel.id] = now
                    else:
                        return
                else:
                    return

        if not is_spontaneous:
            last_used = self.cooldowns.get(message.author.id, 0.0)
            if now - last_used < self.cooldown_seconds:
                return
            if len(self.cooldowns) > 2000:
                self.cooldowns = {uid: ts for uid, ts in self.cooldowns.items() if (now - ts) < 60.0}
            self.cooldowns[message.author.id] = now

        clean_text = message.content
        for mention_str in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            clean_text = clean_text.replace(mention_str, "")
        clean_text = clean_text.strip()

        if message.embeds:
            emb_text = self._extract_embeds_text(message.embeds)
            if emb_text:
                clean_text = f"{clean_text}\n{emb_text}".strip()

        if ref_msg:
            ref_parts = []
            if ref_msg.content:
                ref_parts.append(ref_msg.content[:600])
            if ref_msg.embeds:
                ref_parts.append(self._extract_embeds_text(ref_msg.embeds))
            if ref_parts:
                quoted_combined = " | ".join(ref_parts)
                clean_text = (
                    f"(В ответ на сообщение от {ref_msg.author.display_name} [ID: {ref_msg.author.id}]: "
                    f"«{quoted_combined}») {clean_text}"
                ).strip()

        target_attachment: Optional[disnake.Attachment] = None
        target_embed_img_url: Optional[str] = None

        if message.attachments:
            target_attachment = message.attachments[0]
        elif ref_msg and ref_msg.attachments:
            target_attachment = ref_msg.attachments[0]
        elif message.embeds:
            target_embed_img_url = self._extract_embed_image_url(message.embeds)
        elif ref_msg and ref_msg.embeds:
            target_embed_img_url = self._extract_embed_image_url(ref_msg.embeds)

        if not clean_text and not target_attachment and not target_embed_img_url:
            if not is_spontaneous:
                await message.reply("💠 Я тут, чего звал?", mention_author=False)
            return

        if not clean_text and (target_attachment or target_embed_img_url):
            clean_text = "Посмотри на это изображение и прокомментируй его!"

        async with message.channel.typing():
            image_data = None
            if target_attachment or target_embed_img_url:
                image_data = await self._download_image_base64(target_attachment, target_embed_img_url)

            reply_text = await self._ask_llm(
                guild=message.guild,
                channel=message.channel,
                author=message.author,
                user_text=clean_text[:1500],
                image_data=image_data,
                is_spontaneous=is_spontaneous
            )

        if reply_text:
            # 1. Извлекаем и ставим реакцию, если нейросеть её добавила
            react_match = re.search(r"\[REACT:\s*([^\]]+)\]", reply_text)
            if react_match:
                emoji_str = react_match.group(1).strip()
                reply_text = re.sub(r"\[REACT:\s*[^\]]+\]", "", reply_text).strip()
                try:
                    await message.add_reaction(emoji_str)
                except disnake.HTTPException:
                    pass

            # 2. Извлекаем и выполняем действие модерации (только если это прямой запрос, не спонтанный)
            action_status = ""
            action_match = re.search(r"\[ACTION:\s*([^\]]+)\]", reply_text)
            if action_match:
                raw_action = action_match.group(1).strip()
                reply_text = re.sub(r"\[ACTION:\s*[^\]]+\]", "", reply_text).strip()
                if not is_spontaneous:
                    action_status = await self._execute_ai_action(message, raw_action)

            final_output = f"{reply_text}\n\n{action_status}".strip() if action_status else reply_text
            if final_output:
                await message.reply(final_output[:2000], mention_author=False)
        elif not is_spontaneous:
            await message.reply("⚠️ Модули нейросети временно недоступны, попробуй чуть позже.", mention_author=False)

    # -------------------------------------------------------------------------
    # ЕДИНАЯ КОМАНДА УПРАВЛЕНИЯ ИИ (/ai) — ТОЛЬКО ДЛЯ АДМИНИСТРАТОРОВ
    # -------------------------------------------------------------------------
    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ai",
        description="💠 Управление ИИ Mirei (Только для администраторов)"
    )
    @commands.default_member_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    async def ai_control_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model: Optional[str] = commands.Param(
            default=None,
            choices={
                "🔄 Авто-выбор (Все модели)": "auto",
                "✨ Google Gemini": "gemini",
                "🟢 ChatGPT (GPT-4o-mini)": "chatgpt",
                "🐋 DeepSeek V3": "deepseek",
                "🌪️ Mistral AI": "mistral",
            },
            description="Быстро сменить модель нейросети"
        ),
        auto_reply_chance: Optional[int] = commands.Param(
            default=None,
            description="Шанс случайного ответа в обычный чат (0-100%, 0 = выкл)",
            ge=0,
            le=100
        ),
        enabled: Optional[bool] = commands.Param(
            default=None,
            description="Включить (True) или выключить (False) ИИ на сервере"
        ),
        reset_memory: bool = commands.Param(
            default=False,
            description="Очистить память диалога в текущем канале?"
        )
    ):
        await self._ensure_creator_id()
        if not inter.author.guild_permissions.administrator and inter.author.id not in self.creator_ids:
            await inter.response.send_message(
                "⛔ Доступ запрещен: управлять модулем ИИ могут только администраторы сервера.",
                ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)

        updates = {}
        if model is not None:
            updates["aiProvider"] = model
        if auto_reply_chance is not None:
            updates["aiAutoReplyChance"] = auto_reply_chance
        if enabled is not None:
            updates["aiEnabled"] = enabled
        if reset_memory:
            self._clear_channel_memory(inter.channel_id)

        if updates:
            await self.update_ai_config(inter.guild_id, **updates)

        cfg = await self.get_ai_config(inter.guild_id)
        view = AIControlPanelView(self, inter.author.id, inter.guild_id, inter.channel_id, cfg)
        embed = await view.build_embed(inter.guild)
        await inter.edit_original_response(embed=embed, view=view)


def setup(bot: commands.Bot):
    bot.add_cog(AIChat(bot))