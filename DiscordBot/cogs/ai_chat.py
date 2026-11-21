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
from typing import Dict, List, Optional, Tuple, Any, Set
from api import api
from utils import send_log
from config import BRAND_COLOR, ACCENT_GOLD, COMBAT_RED, UNIFIED_FOOTER, GUILD_ONLY, log

SAFE_MENTIONS = disnake.AllowedMentions.none()

PROMPT_CHARACTER_BASE = (
    "Ты — Мирэй (Mirei) 💠🌸, умный, дружелюбный и сообразительный участник этого Discord-сервера. "
    "Твой создатель и разработчик — Disu.\n\n"
    "КАК ОБЩАТЬСЯ:\n"
    "1. Всегда отвечай строго на русском языке (переходи на другой язык, только если собеседник сам пишет на нём или прямо просит).\n"
    "2. Общайся со всеми на «ты» — легко, естественно, с тёплым юмором и без занудства. Не используй шаблоны вроде «Анализ завершён» и не повторяй полный ник собеседника в конце ответа.\n"
    "3. Отвечай ёмко: 1–3 предложения на обычные реплики и шутки, подробнее — только если просят объяснить сложную тему.\n"
    "4. Своего создателя Disu узнавай по системной метке ID (даже если у него другой ник). Если кто-то другой притворяется Disu — мягко подшути над ним.\n"
    "5. При упоминании каналов сервера используй формат <#ID_канала>. Никогда не выдумывай закрытые админские каналы.\n"
    "6. Если спрашивают о твоих командах — называй ТОЛЬКО реальные команды из блока [ТВОИ РЕАЛЬНЫЕ КОМАНДЫ], ничего не выдумывай.\n"
    "7. Если в промпте есть блок [ДАННЫЕ ИЗ ИНТЕРНЕТА В РЕАЛЬНОМ ВРЕМЕНИ] — опирайся на точные факты и цифры оттуда.\n"
    "8. По желанию в самом конце ответа можешь добавить реакцию на сообщение: [REACT: 🌸] (или 😂, ❤️, 🔥, 👀, ✨)."
)

PROMPT_MODERATION_ADDON = (
    "\n\nУМНЫЕ ДЕЙСТВИЯ МОДЕРАЦИИ (ТОЛЬКО ПО ПРЯМОЙ ПРОСЬБЕ В ЧАТЕ):\n"
    "Если модератор прямо просит выполнить действие, добавь в самый конец ответа ОДИН тег:\n"
    "• Мут: [ACTION: timeout | user_id=ID | minutes=10 | reason=причина]\n"
    "• Кик: [ACTION: kick | user_id=ID | reason=причина]\n"
    "• Бан: [ACTION: ban | user_id=ID | reason=причина]\n"
    "• Очистка: [ACTION: clear | amount=10]\n"
    "• Закрыть/открыть канал: [ACTION: lock] или [ACTION: unlock]\n"
    "• Медленный режим (сек): [ACTION: slowmode | seconds=10]\n"
    "Никогда не придумывай ID сам — бери только из упоминания (<@ID>) или цитаты! Если ID не указан — попроси тегнуть нарушителя."
)

# Список моделей Gemini по умолчанию (можно переопределить через GEMINI_MODELS в .env)
DEFAULT_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

# Единая таблица официальных OpenAI-совместимых провайдеров (с бесплатным тиром по официальным ключам)
OPENAI_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "groq": {
        "label": "⚡ Groq (Llama 3.3 70B — сверхбыстрый)",
        "desc": "Молниеносный бесплатный API от Groq",
        "emoji": "⚡",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    },
    "openrouter": {
        "label": "🌐 OpenRouter Free (DeepSeek / Llama)",
        "desc": "Бесплатные модели через официальный OpenRouter",
        "emoji": "🌐",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            "openrouter/free",
            "deepseek/deepseek-chat:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ],
    },
    "mistral": {
        "label": "🌪️ Mistral AI (Официальный API)",
        "desc": "Бесплатный тариф Mistral La Plateforme",
        "emoji": "🌪️",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "env_key": "MISTRAL_API_KEY",
        "models": ["mistral-small-latest"],
    },
}

PROVIDER_NAMES = {
    "auto": "🔄 Авто-выбор (Все доступные)",
    "gemini": "✨ Google Gemini (Текст + Картинки)",
    **{k: v["label"] for k, v in OPENAI_PROVIDERS.items()},
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

# Лимиты, таймауты и кэши
MEMORY_TTL_SECONDS = 3600
MAX_MEMORY_CHANNELS = 500
AI_CFG_CACHE_TTL = 45.0
CHANNELS_CACHE_TTL = 60.0
RULES_CACHE_TTL = 1800.0
MAX_RULES_CACHE_GUILDS = 500
RATES_CACHE_TTL_SECONDS = 900.0
AUTO_REPLY_CHANNEL_COOLDOWN = 180.0
MODEL_COOLDOWN_TEMP = 300.0         # 5 минут пропуска при 429 / 5xx / таймауте
MODEL_COOLDOWN_NOT_FOUND = 3600.0   # 1 час пропуска при 404
TOTAL_LLM_TIMEOUT = 30.0            # Общий предел ожидания ответа ИИ
MAX_OUTPUT_TOKENS = 500             # Оптимально для быстрых ответов в 1-3 предложения
DM_DAILY_LIMIT = 20                 # Дневной лимит сообщений в ЛС (кроме создателя)

WMO_WEATHER_CODES = {
    0: "Ясно ☀️", 1: "Преимущественно ясно 🌤️", 2: "Переменная облачность ⛅", 3: "Пасмурно ☁️",
    45: "Туман 🌫️", 48: "Изморозь 🌫️", 51: "Легкая морось 🌧️", 53: "Морось 🌧️", 55: "Сильная морось 🌧️",
    61: "Небольшой дождь 🌦️", 63: "Дождь 🌧️", 65: "Сильный ливень ⛈️",
    71: "Небольшой снег 🌨️", 73: "Снег ❄️", 75: "Сильный снегопад ❄️", 77: "Снежные зерна ❄️",
    80: "Ливневый дождь 🌦️", 81: "Сильный ливень ⛈️", 82: "Шквалистый ливень ⛈️",
    85: "Снегопад 🌨️", 86: "Сильная метель ❄️", 95: "Гроза ⚡", 96: "Гроза с градом ⛈️", 99: "Сильная гроза с градом ⛈️"
}


class ConfirmModActionView(disnake.ui.View):
    """Кнопка подтверждения для опасных действий модерации (ban / kick) через ИИ."""
    def __init__(self, actor_id: int, action: str, target: disnake.Member, reason: str):
        super().__init__(timeout=30)
        self.actor_id = actor_id
        self.action = action
        self.target = target
        self.reason = reason

    @disnake.ui.button(label="Подтвердить", style=disnake.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.actor_id:
            await inter.response.send_message("⛔ Подтвердить действие может только тот модератор, который его запросил.", ephemeral=True)
            return

        await inter.response.defer()
        guild = inter.guild
        try:
            if self.action == "ban":
                await self.target.ban(reason=f"{self.reason} (ИИ-команда от {inter.author})", clean_history_duration=86400)
                title = "🔨 Участник заблокирован (через ИИ Mirei)"
                text = f"🔨 Участник **{self.target.display_name}** заблокирован на сервере. *(Причина: {self.reason})*"
            else:
                await self.target.kick(reason=f"{self.reason} (ИИ-команда от {inter.author})")
                title = "👢 Участник исключен (через ИИ Mirei)"
                text = f"👢 Участник **{self.target.display_name}** исключен с сервера. *(Причина: {self.reason})*"

            log_embed = disnake.Embed(
                title=title,
                description=f"**Участник:** {self.target.mention} (`{self.target.id}`)\n**Модератор:** {inter.author.mention}\n**Причина:** {self.reason}",
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow()
            )
            log_embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(guild, log_embed)
            await inter.edit_original_response(content=text, view=None, allowed_mentions=SAFE_MENTIONS)
        except disnake.Forbidden:
            await inter.edit_original_response(content="⚠️ У меня недостаточно прав Discord для выполнения этого действия.", view=None)
        except disnake.HTTPException as e:
            await inter.edit_original_response(content=f"❌ Ошибка Discord API: {e}", view=None)

    @disnake.ui.button(label="Отмена", style=disnake.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if inter.author.id != self.actor_id:
            await inter.response.send_message("⛔ Отменить может только автор запроса.", ephemeral=True)
            return
        await inter.response.edit_message(content="↩️ Действие модерации отменено.", view=None)


class AICustomizeModal(disnake.ui.Modal):
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

        saved = await self.cog.update_ai_config(
            guild_id,
            aiCustomScenario=scenario or None,
            aiCustomRules=rules or None
        )
        self.cog._clear_channel_memory(inter.channel_id)

        embed = await self.panel_view.build_embed(inter.guild)
        warn = None if saved else "⚠️ Не удалось сохранить в БД — применено временно в памяти."
        await inter.edit_original_response(content=warn, embed=embed, view=self.panel_view)


class AIControlPanelView(disnake.ui.View):
    """Панель управления ИИ (динамически показывает только реально подключённые провайдеры)."""
    def __init__(self, cog: "AIChat", author_id: int, guild_id: int, channel_id: int, current_cfg: Dict[str, Any]):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.channel_id = channel_id

        # Динамический список только реально настроенных провайдеров (без обмана админов)
        provider_options = [
            disnake.SelectOption(
                label="Авто-выбор (Все доступные)",
                value="auto",
                emoji="🔄",
                description="Автоматический перебор настроенных API"
            )
        ]
        if cog.gemini_key:
            provider_options.append(disnake.SelectOption(
                label="Google Gemini",
                value="gemini",
                emoji="✨",
                description="Быстрая + понимает картинки и мемы"
            ))
        for p_key, p_meta in OPENAI_PROVIDERS.items():
            if cog.provider_keys.get(p_key):
                provider_options.append(disnake.SelectOption(
                    label=p_meta["label"][:100],
                    value=p_key,
                    emoji=p_meta["emoji"],
                    description=p_meta["desc"][:100]
                ))

        self.provider_select = disnake.ui.Select(
            placeholder="🧠 Выберите модель нейросети...",
            options=provider_options,
            row=0,
        )
        self.provider_select.callback = self._on_provider_select
        self.add_item(self.provider_select)

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

    async def _on_provider_select(self, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()
        chosen = self.provider_select.values[0]
        saved = await self.cog.update_ai_config(self.guild_id, aiProvider=chosen)
        embed = await self.build_embed(inter.guild)
        warn = None if saved else "⚠️ Ошибка сохранения в БД — применено временно."
        await inter.edit_original_response(content=warn, embed=embed, view=self)

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
        saved = await self.cog.update_ai_config(self.guild_id, aiAutoReplyChance=chosen_chance)
        embed = await self.build_embed(inter.guild)
        warn = None if saved else "⚠️ Ошибка сохранения в БД — применено временно."
        await inter.edit_original_response(content=warn, embed=embed, view=self)

    @disnake.ui.button(label="Выключить ИИ", style=disnake.ButtonStyle.danger, emoji="🔴", row=2)
    async def toggle_btn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()
        cfg = await self.cog.get_ai_config(self.guild_id)
        new_state = not (cfg.get("aiEnabled", True) is not False)
        saved = await self.cog.update_ai_config(self.guild_id, aiEnabled=new_state)
        embed = await self.build_embed(inter.guild)
        warn = None if saved else "⚠️ Ошибка сохранения в БД — применено временно."
        await inter.edit_original_response(content=warn, embed=embed, view=self)

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

        # Официальные бесплатные API-ключи из .env
        self.gemini_key = (os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        self.provider_keys: Dict[str, str] = {
            name: (os.getenv(meta["env_key"]) or "").strip()
            for name, meta in OPENAI_PROVIDERS.items()
        }

        # Список моделей Gemini (можно задать через GEMINI_MODELS="gemini-2.5-flash,gemini-2.0-flash")
        env_gemini = (os.getenv("GEMINI_MODELS") or "").strip()
        self.gemini_models: List[str] = (
            [m.strip() for m in env_gemini.split(",") if m.strip()]
            if env_gemini else list(DEFAULT_GEMINI_MODELS)
        )
        self._gemini_models_verified = False

        env_creator = (os.getenv("CREATOR_ID") or "").strip()
        self.creator_ids: set[int] = {int(env_creator)} if env_creator.isdigit() else set()
        self._creator_fetched = False

        self._session: Optional[aiohttp.ClientSession] = None

        # Память диалогов и кэши с TTL
        self.memory: Dict[int, deque] = {}
        self._memory_last_active: Dict[int, float] = {}
        self._ai_cfg_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._channels_cache: Dict[int, Tuple[float, Tuple[List[str], List[str]]]] = {}
        self.rules_cache: Dict[int, Tuple[float, str]] = {}
        self._rates_cache: Optional[Tuple[float, str]] = None

        # Кулдауны и лимит ЛС
        self.cooldowns: Dict[int, float] = {}
        self.cooldown_seconds = 3.0
        self._channel_auto_cooldowns: Dict[int, float] = {}
        self._dm_daily_usage: Dict[int, Tuple[str, int]] = {}  # user_id -> (YYYY-MM-DD, count)

        # Предохранитель (Circuit Breaker) по каждой отдельной модели: "provider:model" -> until_ts
        self._model_cooldowns: Dict[str, float] = {}

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    def _is_model_available(self, key: str) -> bool:
        return time.time() >= self._model_cooldowns.get(key, 0.0)

    def _ban_model(self, key: str, seconds: float):
        self._model_cooldowns[key] = time.time() + seconds

    def _clear_channel_memory(self, channel_id: int):
        self.memory.pop(channel_id, None)
        self._memory_last_active.pop(channel_id, None)

    def _get_channel_history(self, channel_id: int) -> deque:
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
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    @commands.Cog.listener()
    async def on_ready(self):
        """При старте проверяет существующие модели Gemini через ListModels, чтобы не тратить запросы на 404."""
        await self._verify_gemini_models()

    async def _verify_gemini_models(self):
        if self._gemini_models_verified or not self.gemini_key:
            return
        try:
            session = await self._get_session()
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": self.gemini_key}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    available = {
                        m.get("name", "").replace("models/", "")
                        for m in (data.get("models") or [])
                        if "generateContent" in (m.get("supportedGenerationMethods") or [])
                    }
                    filtered = [m for m in self.gemini_models if m in available]
                    if filtered:
                        self.gemini_models = filtered
                        log.info("Подтверждённые модели Gemini: %s", ", ".join(self.gemini_models))
                    else:
                        log.warning("Ни одна модель из списка Gemini не найдена в ListModels; оставляем исходный список.")
                    self._gemini_models_verified = True
                else:
                    log.warning("Gemini ListModels вернул статус %s", resp.status)
        except Exception as e:
            log.warning("Не удалось проверить список моделей Gemini: %s", e)

    # -------------------------------------------------------------------------
    # ЧТЕНИЕ И СОХРАНЕНИЕ НАСТРОЕК ИИ С ЛОКАЛЬНЫМ TTL-КЭШЕМ (45 СЕК)
    # -------------------------------------------------------------------------
    async def get_ai_config(self, guild_id: int) -> Dict[str, Any]:
        now = time.time()
        cached = self._ai_cfg_cache.get(guild_id)
        if cached and (now - cached[0]) < AI_CFG_CACHE_TTL:
            return cached[1]

        db_cfg = await api.get_guild_config(str(guild_id)) or {}
        ai_sub = db_cfg.get("ai") or {}
        sec_sub = db_cfg.get("security") or {}

        result = {
            "aiEnabled": ai_sub.get("enabled", True),
            "aiProvider": ai_sub.get("provider") or "auto",
            "aiAutoReplyChance": int(ai_sub.get("autoReplyChance") or 0),
            "aiCustomScenario": ai_sub.get("customScenario"),
            "aiCustomRules": ai_sub.get("customRules"),
            "logChannelId": db_cfg.get("logChannelId"),
            "verificationRoleId": sec_sub.get("verificationRoleId"),
            "trapChannelId": sec_sub.get("trapChannelId"),
        }

        if len(self._ai_cfg_cache) > MAX_RULES_CACHE_GUILDS:
            self._ai_cfg_cache = {gid: v for gid, v in self._ai_cfg_cache.items() if (now - v[0]) < AI_CFG_CACHE_TTL}
        self._ai_cfg_cache[guild_id] = (now, result)
        return result

    async def update_ai_config(self, guild_id: int, **kwargs) -> bool:
        current = dict(await self.get_ai_config(guild_id))
        current.update(kwargs)
        self._ai_cfg_cache[guild_id] = (time.time(), current)

        ai_payload = {
            "enabled": current.get("aiEnabled", True),
            "provider": current.get("aiProvider") or "auto",
            "autoReplyChance": int(current.get("aiAutoReplyChance") or 0),
            "customScenario": current.get("aiCustomScenario"),
            "customRules": current.get("aiCustomRules"),
        }
        return await api.update_ai_config(str(guild_id), ai_payload)

    # -------------------------------------------------------------------------
    # АВТО-ЗНАНИЕ СВОИХ КОМАНД И МЕХАНИК
    # -------------------------------------------------------------------------
    def _build_bot_capabilities(self, user_text: str) -> str:
        cmd_lines: List[str] = []
        short_names: List[str] = []

        for cmd in sorted(self.bot.slash_commands, key=lambda c: c.name):
            is_mod = bool(cmd.default_member_permissions and cmd.default_member_permissions.value != 0)
            tag = " [Персонал]" if is_mod else ""
            children = getattr(cmd, "children", None)
            if children:
                sub_names = ", ".join(sorted(children.keys()))
                short_names.append(f"/{cmd.name} ({sub_names})")
                for sub_name, sub_cmd in sorted(children.items()):
                    desc = getattr(sub_cmd, "description", "") or cmd.description
                    cmd_lines.append(f"• /{cmd.name} {sub_name}{tag} — {desc}")
            else:
                short_names.append(f"/{cmd.name}")
                cmd_lines.append(f"• /{cmd.name}{tag} — {cmd.description}")

        low = user_text.lower()
        need_details = any(k in low for k in (
            "команд", "умеешь", "можешь", "функц", "помог", "настро", "сдела",
            "как работает", "капч", "войс", "статист", "верифи", "роли", "роль",
            "ловуш", "лог", "аудит", "мут", "бан", "кик", "help", "stats", "ai"
        ))

        if not need_details:
            return f"\n[ТВОИ РЕАЛЬНЫЕ КОМАНДЫ: {', '.join(short_names)}]"

        mechanics = (
            "• Верификация и Капча: при включённой капче код спрашивается только у новых аккаунтов (<7 дн.); роли возвращаются из БД.\n"
            "• Приватные войсы: при входе в канал-генератор создаётся личная комната с панелью (замок, имя, кик, лимит), удаляется когда все выходят.\n"
            "• Статистика: счётчики в каналах обновляются автоматически каждые 10 минут.\n"
            "• Канал-ловушка: удаляет сообщения и кикает за любое сообщение."
        )
        return (
            "\n\n[ТВОИ РЕАЛЬНЫЕ КОМАНДЫ]:\n"
            + "\n".join(cmd_lines)
            + f"\n\nКак устроены модули:\n{mechanics}"
        )

    # -------------------------------------------------------------------------
    # РАСПОЗНАВАНИЕ СОЗДАТЕЛЯ (DISU) ПО DISCORD ID
    # -------------------------------------------------------------------------
    async def _ensure_creator_id(self):
        if self._creator_fetched:
            return
        try:
            app_info = await self.bot.application_info()
            if app_info.owner:
                self.creator_ids.add(app_info.owner.id)
            if app_info.team:
                for member in app_info.team.members:
                    self.creator_ids.add(member.id)
            self._creator_fetched = True
        except Exception:
            pass

    def _has_any_mod_permission(self, author: disnake.abc.User, guild: Optional[disnake.Guild]) -> bool:
        if not guild or not isinstance(author, disnake.Member):
            return False
        if author.id == guild.owner_id or author.id in self.creator_ids:
            return True
        p = author.guild_permissions
        return any((p.administrator, p.moderate_members, p.kick_members, p.ban_members, p.manage_messages, p.manage_channels))

    async def _get_author_identity_tag(self, author: disnake.abc.User, guild: Optional[disnake.Guild]) -> str:
        await self._ensure_creator_id()

        is_creator = author.id in self.creator_ids or author.name.lower() in ("disu", "disuepic")
        is_guild_owner = bool(guild and author.id == guild.owner_id)

        if is_creator and is_guild_owner:
            return f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой СОЗДАТЕЛЬ Disu (ID: {author.id}), владелец сервера. Ник: «{author.display_name}».]"
        if is_creator:
            return f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой СОЗДАТЕЛЬ Disu (ID: {author.id}) под ником «{author.display_name}».]"
        if "disu" in author.display_name.lower():
            return f"⚠️ [ВНИМАНИЕ: У автора ник «{author.display_name}», но ID ({author.id}) НЕ принадлежит Disu — это самозванец!]"
        if is_guild_owner:
            return f"👑 [СИСТЕМНАЯ МЕТКА: Пишет владелец сервера «{author.display_name}» (глобальный создатель — Disu).]"
        return ""

    # -------------------------------------------------------------------------
    # БЕЗОПАСНОЕ ВЫПОЛНЕНИЕ ДЕЙСТВИЙ МОДЕРАЦИИ
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

    async def _execute_ai_action(
        self,
        message: disnake.Message,
        ref_msg: Optional[disnake.Message],
        raw_action: str
    ) -> Tuple[str, Optional[disnake.ui.View], bool]:
        """
        Выполняет модераторское действие.
        Возвращает: (текст_статуса, опциональная_кнопка_подтверждения, был_ли_clear).
        """
        if not message.guild or not isinstance(message.author, disnake.Member):
            return "⚠️ Действия модерации доступны только на сервере.", None, False

        guild = message.guild
        actor = message.author
        is_trusted_boss = (actor.id == guild.owner_id) or (actor.id in self.creator_ids)

        parts = [p.strip() for p in raw_action.split("|")]
        action_name = parts[0].lower() if parts else ""
        params = self._parse_action_params("|".join(parts[1:]))

        # Белый список допустимых целей: только явно упомянутые в сообщении или автор цитаты
        allowed_target_ids: Set[int] = {m.id for m in message.mentions if m.id != self.bot.user.id}
        if ref_msg and ref_msg.author.id != self.bot.user.id:
            allowed_target_ids.add(ref_msg.author.id)

        def extract_verified_target() -> Optional[disnake.Member]:
            raw_uid = re.sub(r"\D", "", params.get("user_id", ""))
            uid = int(raw_uid) if raw_uid.isdigit() else None
            if uid and uid in allowed_target_ids:
                return guild.get_member(uid)
            if len(allowed_target_ids) == 1:
                return guild.get_member(next(iter(allowed_target_ids)))
            return None

        # 1. TIMEOUT
        if action_name == "timeout":
            if not (is_trusted_boss or actor.guild_permissions.moderate_members):
                return "⛔ У тебя нет прав на таймаут участников.", None, False
            target = extract_verified_target()
            if not target:
                return "⚠️ Чтобы выдать таймаут, явно тегни участника (`@ник`) или ответь на его сообщение.", None, False
            if err := self._can_moderate_target(guild, actor, target):
                return f"⛔ Не могу выполнить: {err}.", None, False

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
                return f"✅ Готово! **{target.display_name}** отправлен в таймаут на **{mins} мин.** *(Причина: {reason})*", None, False
            except disnake.Forbidden:
                return "⚠️ У меня не хватает прав Discord для выдачи таймаута.", None, False

        # 2. KICK / BAN (ТОЛЬКО ЧЕРЕЗ КНОПКУ ПОДТВЕРЖДЕНИЯ!)
        if action_name in ("kick", "ban"):
            has_perm = (
                is_trusted_boss
                or (action_name == "kick" and actor.guild_permissions.kick_members)
                or (action_name == "ban" and actor.guild_permissions.ban_members)
            )
            if not has_perm:
                return f"⛔ У тебя нет прав на `{action_name}` участников.", None, False

            target = extract_verified_target()
            if not target:
                return "⚠️ Чтобы выполнить действие, явно тегни участника (`@ник`) или ответь на его сообщение.", None, False
            if err := self._can_moderate_target(guild, actor, target):
                return f"⛔ Не могу выполнить: {err}.", None, False

            default_reason = "Заблокирован через Mirei" if action_name == "ban" else "Исключен через Mirei"
            reason = (params.get("reason") or default_reason)[:200]
            verb = "заблокировать (БАН)" if action_name == "ban" else "исключить (КИК)"
            view = ConfirmModActionView(actor.id, action_name, target, reason)
            return f"⚠️ Подтверди действие: **{verb}** участника **{target.display_name}** (`{target.id}`)?\n*Причина: {reason}*", view, False

        # 3. CLEAR (oldest_first=False, чтобы удалять именно ПОСЛЕДНИЕ сообщения!)
        if action_name == "clear":
            if not (is_trusted_boss or actor.guild_permissions.manage_messages):
                return "⛔ У тебя нет прав на удаление сообщений.", None, False
            try:
                amount = max(1, min(100, int(re.sub(r"\D", "", params.get("amount", "10")) or "10")))
            except ValueError:
                amount = 10

            cutoff = disnake.utils.utcnow() - datetime.timedelta(days=14)
            try:
                deleted = await message.channel.purge(limit=amount + 1, after=cutoff, oldest_first=False)
                count = max(0, len(deleted) - 1)
                return f"🧹 Очистила последние **{count}** сообщений в этом канале!", None, True
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на удаление сообщений в этом канале.", None, False

        # 4. LOCK / UNLOCK
        if action_name in ("lock", "unlock"):
            if not (is_trusted_boss or actor.guild_permissions.manage_channels):
                return "⛔ У тебя нет прав на управление каналами.", None, False
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
                return ("🔒 Канал закрыт для сообщений." if is_lock else "🔓 Канал снова открыт для общения!"), None, False
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на изменение разрешений этого канала.", None, False

        # 5. SLOWMODE
        if action_name == "slowmode":
            if not (is_trusted_boss or actor.guild_permissions.manage_channels):
                return "⛔ У тебя нет прав на управление каналами.", None, False
            try:
                sec = max(0, min(21600, int(re.sub(r"\D", "", params.get("seconds", "0")) or "0")))
            except ValueError:
                sec = 0
            try:
                await message.channel.edit(slowmode_delay=sec)
                return ("⚡ Медленный режим отключён." if sec == 0 else f"⏳ Медленный режим включён: **1 сообщение в {sec} сек.**"), None, False
            except disnake.Forbidden:
                return "⚠️ У меня нет прав на изменение настроек канала.", None, False

        return "", None, False

    # -------------------------------------------------------------------------
    # ЧТЕНИЕ EMBED-СООБЩЕНИЙ И КАРТИНОК
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_embeds_text(embeds: List[disnake.Embed]) -> str:
        if not embeds:
            return ""
        parts = []
        for idx, emb in enumerate(embeds[:2], 1):
            items = []
            if emb.author and emb.author.name:
                items.append(f"Автор: {emb.author.name}")
            if emb.title:
                items.append(f"Заголовок: {emb.title}")
            if emb.description:
                items.append(f"Текст: {emb.description[:800]}")
            for f in emb.fields[:6]:
                items.append(f"{f.name}: {f.value[:200]}")
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
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=7)) as resp:
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
    # СБОР ЗНАНИЙ О СЕРВЕРЕ (КОМПАКТНО + КЭШ КАНАЛОВ НА 60 СЕК)
    # -------------------------------------------------------------------------
    async def _get_server_rules_text(self, guild: disnake.Guild, cfg: Dict[str, Any]) -> str:
        custom = cfg.get("aiCustomRules")
        if custom:
            return custom[:1500]

        now = time.time()
        cached = self.rules_cache.get(guild.id)
        if cached and (now - cached[0]) < RULES_CACHE_TTL:
            return cached[1]

        if len(self.rules_cache) > MAX_RULES_CACHE_GUILDS:
            self.rules_cache = {gid: v for gid, v in self.rules_cache.items() if (now - v[0]) < RULES_CACHE_TTL}

        rules_channel: Optional[disnake.TextChannel] = guild.rules_channel
        if not rules_channel:
            for ch in guild.text_channels:
                if any(k in ch.name.lower() for k in ("правил", "rules", "устав")):
                    rules_channel = ch
                    break

        if not rules_channel:
            text = "Специальный канал правил не найден, действуют общие нормы адекватности."
            self.rules_cache[guild.id] = (now, text)
            return text

        collected = []
        try:
            async for msg in rules_channel.history(limit=5, oldest_first=True):
                if msg.content:
                    collected.append(msg.content[:1000])
                if msg.embeds:
                    collected.append(self._extract_embeds_text(msg.embeds))
        except disnake.HTTPException:
            pass

        rules_text = "\n".join(collected)[:1500] if collected else f"Правила находятся в канале {rules_channel.mention}."
        self.rules_cache[guild.id] = (now, rules_text)
        return rules_text

    def _get_public_channels_cached(self, guild: disnake.Guild, cfg: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        now = time.time()
        cached = self._channels_cache.get(guild.id)
        if cached and (now - cached[0]) < CHANNELS_CACHE_TTL:
            return cached[1]

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
                topic_str = f" ({ch.topic[:40]})" if ch.topic else ""
                nsfw_tag = " [18+]" if ch.is_nsfw() else ""
                text_ch_list.append(f"<#{ch.id}> (#{ch.name}{nsfw_tag}{topic_str})")
                if len(text_ch_list) >= 15:
                    break

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
                if len(voice_ch_list) >= 10:
                    break

        if len(self._channels_cache) > MAX_RULES_CACHE_GUILDS:
            self._channels_cache = {gid: v for gid, v in self._channels_cache.items() if (now - v[0]) < CHANNELS_CACHE_TTL}
        self._channels_cache[guild.id] = (now, (text_ch_list, voice_ch_list))
        return text_ch_list, voice_ch_list

    async def _build_guild_knowledge(
        self,
        guild: Optional[disnake.Guild],
        current_channel: disnake.abc.Messageable,
        cfg: Dict[str, Any]
    ) -> str:
        if not guild:
            return "Диалог идет в личных сообщениях (DM). Твой создатель — Disu."

        owner_str = f"{guild.owner.display_name} (<@{guild.owner.id}>)" if guild.owner else f"<@{guild.owner_id}>"
        text_ch_list, voice_ch_list = self._get_public_channels_cached(guild, cfg)

        text_summary = ", ".join(text_ch_list) if text_ch_list else "Нет доступных"
        voice_summary = ", ".join(voice_ch_list) if voice_ch_list else "Нет доступных"
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
    # ВЫХОД В ИНТЕРНЕТ (ИСПРАВЛЕННАЯ РЕГУЛЯРКА + ДИНАМИЧЕСКИЙ ГОД)
    # -------------------------------------------------------------------------
    async def _fetch_weather(self, text: str) -> Optional[str]:
        clean = re.sub(
            r"\b(?:какая|какой|сейчас|сегодня|завтра|загугли|найди|скажи|покажи|погода|погоду|градусов|температура|в|во|на)\b",
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
            async with session.get(nom_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
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
            async with session.get(w_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
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
                async with session.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = json.loads(await resp.text())
                        val = data.get("Valute", {})
                        usd = val.get("USD", {}).get("Value")
                        eur = val.get("EUR", {}).get("Value")
                        cny = val.get("CNY", {}).get("Value")
                        kzt = val.get("KZT", {}).get("Value")
                        if usd and eur:
                            return (
                                f"Курс ЦБ РФ: 1 USD = {usd:.2f} руб., 1 EUR = {eur:.2f} руб., "
                                f"1 CNY = {cny:.2f} руб., 100 KZT = {kzt:.2f} руб."
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
                            return f"Крипта: BTC = ${btc_usd:,}, TON = ${ton_usd} ({ton_rub} руб.)."
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
            r"\b(?:загугли|найди в интернете|найди в инете|найди|поищи|расскажи про|что такое|кто такой)\b",
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
                async with session.get(g_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
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
                async with session.get(w_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
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

    async def _gather_internet_context(self, raw_user_text: str) -> str:
        low = raw_user_text.lower()
        blocks = []

        if any(w in low for w in ("погод", "градус", "температур", "дождь в", "снег в", "метео")):
            weather_info = await self._fetch_weather(raw_user_text)
            if weather_info:
                blocks.append(weather_info)

        if any(w in low for w in ("курс", "доллар", "евро", "рубл", "юан", "тенге", "биткоин", "btc", "крипт", "ton ")):
            rates_info = await self._fetch_currency_rates()
            if rates_info:
                blocks.append(rates_info)

        cur_year = datetime.datetime.now().year
        search_triggers = (
            "загугли", "найди", "поищи", "новости", "когда выйдет", "когда вышел",
            "кто выиграл", "что случилось", "кто такой", "что такое", "актуальн",
            f"в {cur_year}", f"в {cur_year - 1}", f"в {cur_year + 1}"
        )
        if any(w in low for w in search_triggers) and not blocks:
            web_info = await self._fetch_web_search(raw_user_text)
            if web_info:
                blocks.append(web_info)

        if not blocks:
            return ""

        return "\n\n[ДАННЫЕ ИЗ ИНТЕРНЕТА В РЕАЛЬНОМ ВРЕМЕНИ]:\n" + "\n".join(blocks)

    # =========================================================================
    # ОФИЦИАЛЬНЫЕ ПРОВАЙДЕРЫ: GEMINI + ЕДИНЫЙ OPENAI-СОВМЕСТИМЫЙ КЛИЕНТ
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

        if not self._gemini_models_verified:
            await self._verify_gemini_models()

        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        user_parts: List[dict] = [{"text": current_msg}]
        if image_data:
            mime_type, b64_str = image_data
            user_parts.append({"inlineData": {"mimeType": mime_type, "data": b64_str}})

        contents.append({"role": "user", "parts": user_parts})

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.gemini_key,
        }
        req_timeout = aiohttp.ClientTimeout(total=13 if image_data else 9)
        session = await self._get_session()

        for model_name in self.gemini_models:
            ban_key = f"gemini:{model_name}"
            if not self._is_model_available(ban_key):
                continue

            gen_config: Dict[str, Any] = {
                "temperature": 0.85,
                "maxOutputTokens": 800,
            }
            # Для серии Gemini 3.x задаём минимальную глубину размышлений для быстрого отклика
            if "3.8" in model_name:
                gen_config["thinkingConfig"] = {"thinkingLevel": "low"}
            elif model_name.startswith("gemini-3"):
                gen_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
            
            payload: Dict[str, Any] = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "safetySettings": SAFETY_SETTINGS_MODERATE,
                "generationConfig": gen_config,
            }

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                async with session.post(url, json=payload, headers=headers, timeout=req_timeout) as resp:
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
                    elif resp.status == 404:
                        err = await resp.text()
                        log.warning("Gemini модель %s не найдена (404), пропускаем на 1 ч: %s", model_name, err[:150])
                        self._ban_model(ban_key, MODEL_COOLDOWN_NOT_FOUND)
                    elif resp.status in (429, 500, 503):
                        err = await resp.text()
                        log.warning("Gemini %s вернула %s, пауза 5 мин: %s", model_name, resp.status, err[:150])
                        self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
                    else:
                        err = await resp.text()
                        log.warning("Gemini %s ошибка %s: %s", model_name, resp.status, err[:200])
                        self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
            except asyncio.TimeoutError:
                log.warning("Таймаут Gemini %s, пауза 5 мин.", model_name)
                self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
            except Exception as e:
                log.warning("Сбой запроса Gemini %s: %s", model_name, e)
                self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)

        return None

    async def _call_openai_provider(
        self,
        provider_name: str,
        system_prompt: str,
        history: deque,
        current_msg: str
    ) -> Optional[str]:
        meta = OPENAI_PROVIDERS.get(provider_name)
        api_key = self.provider_keys.get(provider_name)
        if not meta or not api_key:
            return None

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": current_msg})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req_timeout = aiohttp.ClientTimeout(total=9)
        session = await self._get_session()

        for model_name in meta["models"]:
            ban_key = f"{provider_name}:{model_name}"
            if not self._is_model_available(ban_key):
                continue

            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": MAX_OUTPUT_TOKENS,
            }
            try:
                async with session.post(meta["url"], json=payload, headers=headers, timeout=req_timeout) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception:
                            log.warning("Провайдер %s (%s) вернул не-JSON ответ.", provider_name, model_name)
                            self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
                            continue
                        choices = data.get("choices") or []
                        if choices:
                            reply = (choices[0].get("message", {}).get("content") or "").strip()
                            if reply:
                                return reply
                    elif resp.status == 404:
                        log.warning("%s (%s) вернул 404, пауза 1 ч.", provider_name, model_name)
                        self._ban_model(ban_key, MODEL_COOLDOWN_NOT_FOUND)
                    else:
                        err = await resp.text()
                        log.warning("%s (%s) вернул %s: %s", provider_name, model_name, resp.status, err[:150])
                        self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
            except asyncio.TimeoutError:
                log.warning("Таймаут %s (%s), пауза 5 мин.", provider_name, model_name)
                self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)
            except Exception as e:
                log.warning("Ошибка %s (%s): %s", provider_name, model_name, e)
                self._ban_model(ban_key, MODEL_COOLDOWN_TEMP)

        return None

    # -------------------------------------------------------------------------
    # ГЛАВНЫЙ МАРШРУТИЗАТОР ЗАПРОСОВ К ИИ (С ПАРАЛЛЕЛЬНОЙ ПОДГОТОВКОЙ И ОБЩИМ ТАЙМАУТОМ)
    # -------------------------------------------------------------------------
    async def _ask_llm_inner(
        self,
        guild: Optional[disnake.Guild],
        channel: disnake.abc.Messageable,
        author: disnake.abc.User,
        user_text: str,
        raw_user_text: str,
        attachment: Optional[disnake.Attachment],
        embed_img_url: Optional[str],
        is_spontaneous: bool
    ) -> Optional[str]:
        guild_id = guild.id if guild else 0
        channel_id = getattr(channel, "id", 0)
        history = self._get_channel_history(channel_id)

        cfg = await self.get_ai_config(guild_id) if guild else {}

        # Параллельно собираем контекст сервера, метку личности, данные из интернета и картинку
        async def empty_none():
            return None

        async def empty_str():
            return ""

        guild_knowledge_coro = self._build_guild_knowledge(guild, channel, cfg)
        identity_coro = self._get_author_identity_tag(author, guild)
        internet_coro = empty_str() if is_spontaneous else self._gather_internet_context(raw_user_text)
        image_coro = (
            self._download_image_base64(attachment, embed_img_url)
            if (attachment or embed_img_url) else empty_none()
        )

        guild_knowledge, identity_tag, internet_context, image_data = await asyncio.gather(
            guild_knowledge_coro, identity_coro, internet_coro, image_coro
        )

        # Стабильная часть промпта — в начале (для кэширования префикса у Gemini)
        base_prompt = PROMPT_CHARACTER_BASE
        if not is_spontaneous and self._has_any_mod_permission(author, guild):
            base_prompt += PROMPT_MODERATION_ADDON

        custom_scenario = cfg.get("aiCustomScenario")
        if custom_scenario:
            base_prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ СЦЕНАРИЙ ЭТОГО СЕРВЕРА:\n{custom_scenario[:800]}"

        if is_spontaneous:
            base_prompt += (
                "\n\n[КОНТЕКСТ: Тебя сейчас не тегали, ты сама решила по-дружески поддержать беседу. "
                "Ответь коротко в тему (1–2 предложения) и НЕ используй теги ACTION.]"
            )

        bot_capabilities = "" if is_spontaneous else self._build_bot_capabilities(raw_user_text)

        # Динамическая часть (время и свежие данные из сети) — строго в самом конце промпта
        msk_tz = datetime.timezone(datetime.timedelta(hours=3))
        now_msk = datetime.datetime.now(msk_tz)
        time_info = now_msk.strftime(f"{WEEKDAYS_RU[now_msk.weekday()]}, %d.%m.%Y, %H:%M (МСК)")

        active_prompt = (
            f"{base_prompt}\n"
            f"{guild_knowledge}"
            f"{bot_capabilities}\n"
            f"Текущее время и дата: {time_info}."
            f"{internet_context}"
        )

        author_header = f"{author.display_name} (ID: {author.id})"
        current_msg = f"{identity_tag}\n{author_header}: {user_text}".strip() if identity_tag else f"{author_header}: {user_text}"

        # Формируем порядок только из реально настроенных провайдеров
        available_providers: List[str] = []
        if self.gemini_key:
            available_providers.append("gemini")
        for p_name in OPENAI_PROVIDERS:
            if self.provider_keys.get(p_name):
                available_providers.append(p_name)

        preferred = cfg.get("aiProvider") or "auto"
        if preferred in available_providers:
            available_providers.remove(preferred)
            available_providers.insert(0, preferred)

        reply: Optional[str] = None
        for provider_name in available_providers:
            if provider_name == "gemini":
                reply = await self._call_gemini(active_prompt, history, current_msg, image_data)
            elif not image_data:
                reply = await self._call_openai_provider(provider_name, active_prompt, history, current_msg)
            if reply:
                break

        if reply:
            # При спонтанном ответе реплика уже была добавлена в history в on_message — не дублируем!
            if not is_spontaneous:
                history_text = f"{author.display_name}: {user_text} [Изображение]" if image_data else f"{author.display_name}: {user_text}"
                history.append({"role": "user", "content": history_text})
            history.append({"role": "assistant", "content": reply})
            self._memory_last_active[channel_id] = time.time()
            return reply

        return None

    async def _ask_llm(self, **kwargs) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._ask_llm_inner(**kwargs), timeout=TOTAL_LLM_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("Общий таймаут _ask_llm (%s сек) превышен.", TOTAL_LLM_TIMEOUT)
            return None

    # -------------------------------------------------------------------------
    # ОБРАБОТКА СООБЩЕНИЙ
    # -------------------------------------------------------------------------
    @staticmethod
    def _is_ignored_chat_channel(channel: disnake.abc.GuildChannel, guild: disnake.Guild) -> bool:
        if guild.rules_channel and channel.id == guild.rules_channel.id:
            return True
        name_low = getattr(channel, "name", "").lower()
        ignored_words = ("правил", "rules", "логи", "logs", "audit", "аудит", "админ", "admin", "модер", "moder", "тикет", "ticket")
        return any(w in name_low for w in ignored_words)

    def _check_dm_limit(self, user_id: int) -> bool:
        if user_id in self.creator_ids:
            return True
        today = datetime.date.today().isoformat()
        day_str, count = self._dm_daily_usage.get(user_id, (today, 0))
        if day_str != today:
            count = 0
        if count >= DM_DAILY_LIMIT:
            return False
        if len(self._dm_daily_usage) > 2000:
            self._dm_daily_usage = {u: v for u, v in self._dm_daily_usage.items() if v[0] == today}
        self._dm_daily_usage[user_id] = (today, count + 1)
        return True

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

        if is_dm:
            await self._ensure_creator_id()
            if not self._check_dm_limit(message.author.id):
                await message.reply(
                    f"⏳ Дневной лимит сообщений в ЛС исчерпан ({DM_DAILY_LIMIT}/{DM_DAILY_LIMIT}). Приходи завтра или общайся на сервере!",
                    mention_author=False,
                    allowed_mentions=SAFE_MENTIONS,
                )
                return
        else:
            cfg = await self.get_ai_config(message.guild.id)
            if cfg.get("trapChannelId") and str(message.channel.id) == str(cfg["trapChannelId"]):
                return
            if cfg.get("aiEnabled", True) is False:
                return

            is_mentioned = self.bot.user in message.mentions
            is_reply_to_bot = bool(ref_msg and ref_msg.author.id == self.bot.user.id)

            if not (is_mentioned or is_reply_to_bot):
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
                        if len(self._channel_auto_cooldowns) > 2000:
                            self._channel_auto_cooldowns = {
                                cid: ts for cid, ts in self._channel_auto_cooldowns.items()
                                if (now - ts) < AUTO_REPLY_CHANNEL_COOLDOWN
                            }
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

        # Сохраняем чистый текст отдельно (для веб-поиска и погоды без цитат/Embed-ов)
        raw_user_text = message.content
        for mention_str in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            raw_user_text = raw_user_text.replace(mention_str, "")
        raw_user_text = raw_user_text.strip()

        clean_text = raw_user_text
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
                await message.reply("💠 Я тут, чего звал?", mention_author=False, allowed_mentions=SAFE_MENTIONS)
            return

        if not clean_text and (target_attachment or target_embed_img_url):
            clean_text = "Посмотри на это изображение и прокомментируй его!"
            raw_user_text = clean_text

        async with message.channel.typing():
            reply_text = await self._ask_llm(
                guild=message.guild,
                channel=message.channel,
                author=message.author,
                user_text=clean_text[:1500],
                raw_user_text=raw_user_text[:500],
                attachment=target_attachment,
                embed_img_url=target_embed_img_url,
                is_spontaneous=is_spontaneous
            )

        if reply_text:
            react_match = re.search(r"\[REACT:\s*([^\]]+)\]", reply_text)
            if react_match:
                emoji_str = react_match.group(1).strip()
                reply_text = re.sub(r"\[REACT:\s*[^\]]+\]", "", reply_text).strip()
                try:
                    await message.add_reaction(emoji_str)
                except disnake.HTTPException:
                    pass

            action_status = ""
            confirm_view: Optional[disnake.ui.View] = None
            was_clear = False

            action_match = re.search(r"\[ACTION:\s*([^\]]+)\]", reply_text)
            if action_match:
                raw_action = action_match.group(1).strip()
                reply_text = re.sub(r"\[ACTION:\s*[^\]]+\]", "", reply_text).strip()
                if not is_spontaneous:
                    action_status, confirm_view, was_clear = await self._execute_ai_action(message, ref_msg, raw_action)

            final_output = f"{reply_text}\n\n{action_status}".strip() if action_status else reply_text
            if final_output:
                send_kwargs: Dict[str, Any] = {"allowed_mentions": SAFE_MENTIONS}
                if confirm_view is not None:
                    send_kwargs["view"] = confirm_view

                if was_clear:
                    await message.channel.send(final_output[:2000], **send_kwargs)
                else:
                    try:
                        await message.reply(final_output[:2000], mention_author=False, **send_kwargs)
                    except disnake.HTTPException:
                        await message.channel.send(final_output[:2000], **send_kwargs)
        elif not is_spontaneous:
            await message.reply(
                "⚠️ Модули нейросети временно недоступны, попробуй чуть позже.",
                mention_author=False,
                allowed_mentions=SAFE_MENTIONS,
            )

    # -------------------------------------------------------------------------
    # ЕДИНАЯ КОМАНДА УПРАВЛЕНИЯ ИИ (/ai) — АДМИНИСТРАТОРЫ И СОЗДАТЕЛЬ
    # -------------------------------------------------------------------------
    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ai",
        description="💠 Управление ИИ Mirei (Только для администраторов)"
    )
    @commands.default_member_permissions(administrator=True)
    async def ai_control_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model: Optional[str] = commands.Param(
            default=None,
            choices={
                "🔄 Авто-выбор (Все доступные)": "auto",
                "✨ Google Gemini": "gemini",
                "⚡ Groq (Llama 3.3 70B)": "groq",
                "🌐 OpenRouter Free": "openrouter",
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

        # Проверяем, задан ли ключ для выбранной вручную модели
        if model and model != "auto":
            has_key = bool(self.gemini_key) if model == "gemini" else bool(self.provider_keys.get(model))
            if not has_key:
                await inter.edit_original_response(
                    content=f"⚠️ Провайдер **`{model}`** не подключён на сервере (не задан API-ключ в `.env`)."
                )
                return

        updates = {}
        if model is not None:
            updates["aiProvider"] = model
        if auto_reply_chance is not None:
            updates["aiAutoReplyChance"] = auto_reply_chance
        if enabled is not None:
            updates["aiEnabled"] = enabled
        if reset_memory:
            self._clear_channel_memory(inter.channel_id)

        saved = True
        if updates:
            saved = await self.update_ai_config(inter.guild_id, **updates)

        cfg = await self.get_ai_config(inter.guild_id)
        view = AIControlPanelView(self, inter.author.id, inter.guild_id, inter.channel_id, cfg)
        embed = await view.build_embed(inter.guild)
        warn = None if saved else "⚠️ Не удалось сохранить настройки в БД — применено временно."
        await inter.edit_original_response(content=warn, embed=embed, view=view)


def setup(bot: commands.Bot):
    bot.add_cog(AIChat(bot))