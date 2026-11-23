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
from utils import check_moderation_target, send_log
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
    "• Кик: [ACTION: kick | user_id=ID | reason=причина]\n"
    "• Бан: [ACTION: ban | user_id=ID | reason=причина]\n"
    "Никогда не придумывай ID сам — бери только из упоминания (<@ID>) или цитаты! Если ID не указан — попроси тегнуть нарушителя."
)

# Список моделей Gemini можно переопределить через GEMINI_MODELS в .env.
DEFAULT_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

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
    **{key: provider["label"] for key, provider in OPENAI_PROVIDERS.items()},
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
WEEKDAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
]

MEMORY_TTL_SECONDS = 3600
MAX_MEMORY_CHANNELS = 500
AI_CFG_CACHE_TTL = 45.0
CHANNELS_CACHE_TTL = 60.0
RULES_CACHE_TTL = 1800.0
MAX_RULES_CACHE_GUILDS = 500
RATES_CACHE_TTL_SECONDS = 900.0
AUTO_REPLY_CHANNEL_COOLDOWN = 180.0
MODEL_COOLDOWN_TEMP = 300.0
MODEL_COOLDOWN_NOT_FOUND = 3600.0
TOTAL_LLM_TIMEOUT = 30.0
MAX_OUTPUT_TOKENS = 500
DM_DAILY_LIMIT = 20

WMO_WEATHER_CODES = {
    0: "Ясно ☀️",
    1: "Преимущественно ясно 🌤️",
    2: "Переменная облачность ⛅",
    3: "Пасмурно ☁️",
    45: "Туман 🌫️",
    48: "Изморозь 🌫️",
    51: "Легкая морось 🌧️",
    53: "Морось 🌧️",
    55: "Сильная морось 🌧️",
    61: "Небольшой дождь 🌦️",
    63: "Дождь 🌧️",
    65: "Сильный ливень ⛈️",
    71: "Небольшой снег 🌨️",
    73: "Снег ❄️",
    75: "Сильный снегопад ❄️",
    77: "Снежные зерна ❄️",
    80: "Ливневый дождь 🌦️",
    81: "Сильный ливень ⛈️",
    82: "Шквалистый ливень ⛈️",
    85: "Снегопад 🌨️",
    86: "Сильная метель ❄️",
    95: "Гроза ⚡",
    96: "Гроза с градом ⛈️",
    99: "Сильная гроза с градом ⛈️",
}


class ConfirmModActionView(disnake.ui.View):
    def __init__(
        self, actor_id: int, action: str, target: disnake.Member, reason: str
    ):
        super().__init__(timeout=30)
        self.actor_id = actor_id
        self.action = action
        self.target = target
        self.reason = reason

    @disnake.ui.button(
        label="Подтвердить", style=disnake.ButtonStyle.danger, emoji="⚠️"
    )
    async def confirm(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if inter.author.id != self.actor_id:
            await inter.response.send_message(
                "⛔ Подтвердить действие может только модератор, который его запросил.",
                ephemeral=True,
            )
            return

        guild = inter.guild
        permission = "ban_members" if self.action == "ban" else "kick_members"
        target = guild.get_member(self.target.id) if guild else None
        if target is None or not getattr(inter.author.guild_permissions, permission):
            await inter.response.edit_message(
                content="Участник или право модерации недоступны.", view=None
            )
            return
        if error := check_moderation_target(inter, target):
            await inter.response.edit_message(content=error, view=None)
            return

        await inter.response.defer()
        try:
            if self.action == "ban":
                await target.ban(
                    reason=f"{self.reason} (ИИ-команда от {inter.author})",
                    clean_history_duration=86400,
                )
                title = "🔨 Участник заблокирован через Mirei"
                text = (
                    f"🔨 Участник **{target.display_name}** заблокирован на сервере. "
                    f"*(Причина: {self.reason})*"
                )
            else:
                await target.kick(reason=f"{self.reason} (ИИ-команда от {inter.author})")
                title = "👢 Участник исключён через Mirei"
                text = (
                    f"👢 Участник **{target.display_name}** исключён с сервера. "
                    f"*(Причина: {self.reason})*"
                )

            embed = disnake.Embed(
                title=title,
                description=(
                    f"**Участник:** {target.mention} (`{target.id}`)\n"
                    f"**Модератор:** {inter.author.mention}\n"
                    f"**Причина:** {self.reason}"
                ),
                color=COMBAT_RED,
                timestamp=disnake.utils.utcnow(),
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await send_log(guild, embed)
            await inter.edit_original_response(
                content=text, view=None, allowed_mentions=SAFE_MENTIONS
            )
        except disnake.Forbidden:
            await inter.edit_original_response(
                content="⚠️ У бота недостаточно прав Discord для этого действия.",
                view=None,
            )
        except disnake.HTTPException as error:
            await inter.edit_original_response(
                content=f"❌ Ошибка Discord API: {error}", view=None
            )

    @disnake.ui.button(label="Отмена", style=disnake.ButtonStyle.secondary, emoji="✖️")
    async def cancel(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if inter.author.id != self.actor_id:
            await inter.response.send_message(
                "⛔ Отменить действие может только автор запроса.", ephemeral=True
            )
            return

        await inter.response.edit_message(
            content="↩️ Действие модерации отменено.", view=None
        )


class AICustomizeModal(disnake.ui.Modal):
    def __init__(
        self,
        cog: "AIChat",
        panel_view: "AIControlPanelView",
        current_scenario: str,
        current_rules: str,
    ):
        self.cog = cog
        self.panel_view = panel_view
        components = [
            disnake.ui.TextInput(
                label="Сценарий и стиль общения",
                placeholder="Оставьте пустым для стандартного характера Mirei.",
                custom_id="ai_custom_scenario",
                style=disnake.TextInputStyle.paragraph,
                value=current_scenario[:1000] if current_scenario else "",
                required=False,
                max_length=1000,
            ),
            disnake.ui.TextInput(
                label="Правила сервера для ИИ",
                placeholder="Оставьте пустым для чтения из канала правил.",
                custom_id="ai_custom_rules",
                style=disnake.TextInputStyle.paragraph,
                value=current_rules[:1000] if current_rules else "",
                required=False,
                max_length=1000,
            ),
        ]
        super().__init__(title="💠 Сценарий и правила Mirei", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer()
        scenario = inter.text_values.get("ai_custom_scenario", "").strip()
        rules = inter.text_values.get("ai_custom_rules", "").strip()

        guild_id = inter.guild_id
        self.cog.rules_cache.pop(guild_id, None)
        saved = await self.cog.update_ai_config(
            guild_id,
            aiCustomScenario=scenario or None,
            aiCustomRules=rules or None,
        )
        self.cog._clear_channel_memory(inter.channel_id)

        embed = await self.panel_view.build_embed(inter.guild)
        warning = None if saved else "⚠️ Не удалось сохранить настройки в БД."
        await inter.edit_original_response(
            content=warning, embed=embed, view=self.panel_view
        )


class AIControlPanelView(disnake.ui.View):
    def __init__(
        self,
        cog: "AIChat",
        author_id: int,
        guild_id: int,
        channel_id: int,
        current_cfg: Dict[str, Any],
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.channel_id = channel_id

        provider_options = [
            disnake.SelectOption(
                label="Авто-выбор",
                value="auto",
                emoji="🔄",
                description="Перебор настроенных провайдеров",
            )
        ]
        if cog.gemini_key:
            provider_options.append(
                disnake.SelectOption(
                    label="Google Gemini",
                    value="gemini",
                    emoji="✨",
                    description="Текст и изображения",
                )
            )
        for key, provider in OPENAI_PROVIDERS.items():
            if cog.provider_keys.get(key):
                provider_options.append(
                    disnake.SelectOption(
                        label=provider["label"][:100],
                        value=key,
                        emoji=provider["emoji"],
                        description=provider["desc"][:100],
                    )
                )

        self.provider_select = disnake.ui.Select(
            placeholder="🧠 Выбери провайдера", options=provider_options, row=0
        )
        self.provider_select.callback = self._on_provider_select
        self.add_item(self.provider_select)
        self._sync_components(current_cfg)

    def _sync_components(self, cfg: Dict[str, Any]):
        enabled = cfg.get("aiEnabled", True) is not False
        provider = cfg.get("aiProvider") or "auto"
        chance = int(cfg.get("aiAutoReplyChance") or 0)

        self.toggle_btn.label = "Выключить ИИ" if enabled else "Включить ИИ"
        self.toggle_btn.style = (
            disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success
        )
        self.toggle_btn.emoji = "🔴" if enabled else "🟢"

        for option in self.provider_select.options:
            option.default = option.value == provider
        for option in self.chance_select.options:
            option.default = int(option.value) == chance

    async def build_embed(self, guild: disnake.Guild) -> disnake.Embed:
        cfg = await self.cog.get_ai_config(guild.id)
        self._sync_components(cfg)

        enabled = cfg.get("aiEnabled", True) is not False
        provider = cfg.get("aiProvider") or "auto"
        chance = int(cfg.get("aiAutoReplyChance") or 0)
        scenario = cfg.get("aiCustomScenario")
        rules = cfg.get("aiCustomRules")

        status = "🟢 Включён" if enabled else "🔴 Отключён"
        provider_label = PROVIDER_NAMES.get(provider, provider)
        chance_label = CHANCE_LABELS.get(chance, f"{chance}%")
        scenario_label = (
            f"📝 *«{scenario[:120]}{'…' if len(scenario) > 120 else ''}»*"
            if scenario
            else "Стандартный характер Mirei"
        )
        rules_label = (
            f"📝 Заданы вручную ({len(rules)} симв.)"
            if rules
            else "🔍 Чтение из канала правил"
        )

        embed = disnake.Embed(
            title="💠 Настройки ИИ Mirei",
            description=f"Сервер **{guild.name}**",
            color=BRAND_COLOR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="📡 Статус", value=status, inline=False)
        embed.add_field(name="🧠 Провайдер", value=provider_label, inline=True)
        embed.add_field(name="💬 Автоответы", value=chance_label, inline=True)
        embed.add_field(name="🎬 Сценарий", value=scenario_label, inline=False)
        embed.add_field(name="📜 Правила сервера", value=rules_label, inline=False)
        embed.set_footer(text=UNIFIED_FOOTER)
        return embed

    async def _check_access(self, inter: disnake.MessageInteraction) -> bool:
        await self.cog._ensure_creator_id()
        if (
            not inter.author.guild_permissions.administrator
            and inter.author.id not in self.cog.creator_ids
        ):
            await inter.response.send_message(
                "⛔ Управлять этой панелью могут только администраторы сервера.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_provider_select(self, inter: disnake.MessageInteraction):
        if not await self._check_access(inter):
            return
        await inter.response.defer()

        chosen = self.provider_select.values[0]
        saved = await self.cog.update_ai_config(self.guild_id, aiProvider=chosen)
        embed = await self.build_embed(inter.guild)
        warning = None if saved else "⚠️ Ошибка сохранения в БД."
        await inter.edit_original_response(content=warning, embed=embed, view=self)

    @disnake.ui.select(
        placeholder="💬 Настроить шанс автоответа",
        row=1,
        options=[
            disnake.SelectOption(label="Выключено (0%)", value="0", emoji="🔇"),
            disnake.SelectOption(label="Редко (5%)", value="5", emoji="🌱"),
            disnake.SelectOption(label="Средне (10%)", value="10", emoji="💬"),
            disnake.SelectOption(label="Активно (20%)", value="20", emoji="🔥"),
            disnake.SelectOption(label="Очень часто (35%)", value="35", emoji="⚡"),
        ],
    )
    async def chance_select(
        self, select: disnake.ui.Select, inter: disnake.MessageInteraction
    ):
        if not await self._check_access(inter):
            return
        await inter.response.defer()

        chance = int(select.values[0])
        saved = await self.cog.update_ai_config(self.guild_id, aiAutoReplyChance=chance)
        embed = await self.build_embed(inter.guild)
        warning = None if saved else "⚠️ Ошибка сохранения в БД."
        await inter.edit_original_response(content=warning, embed=embed, view=self)

    @disnake.ui.button(
        label="Выключить ИИ", style=disnake.ButtonStyle.danger, emoji="🔴", row=2
    )
    async def toggle_btn(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if not await self._check_access(inter):
            return
        await inter.response.defer()

        cfg = await self.cog.get_ai_config(self.guild_id)
        enabled = cfg.get("aiEnabled", True) is not False
        saved = await self.cog.update_ai_config(self.guild_id, aiEnabled=not enabled)
        embed = await self.build_embed(inter.guild)
        warning = None if saved else "⚠️ Ошибка сохранения в БД."
        await inter.edit_original_response(content=warning, embed=embed, view=self)

    @disnake.ui.button(
        label="Сценарий и правила", style=disnake.ButtonStyle.secondary, emoji="📝", row=2
    )
    async def customize_btn(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if not await self._check_access(inter):
            return

        cfg = await self.cog.get_ai_config(self.guild_id)
        await inter.response.send_modal(
            AICustomizeModal(
                self.cog,
                self,
                cfg.get("aiCustomScenario") or "",
                cfg.get("aiCustomRules") or "",
            )
        )

    @disnake.ui.button(
        label="Очистить память чата", style=disnake.ButtonStyle.secondary, emoji="♻️", row=2
    )
    async def reset_memory_btn(
        self, button: disnake.ui.Button, inter: disnake.MessageInteraction
    ):
        if not await self._check_access(inter):
            return

        self.cog._clear_channel_memory(inter.channel.id)
        await inter.response.send_message(
            "♻️ Память диалога Mirei в этом канале очищена.", ephemeral=True
        )
class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.gemini_key = (os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
        self.provider_keys: Dict[str, str] = {
            name: (os.getenv(meta["env_key"]) or "").strip()
            for name, meta in OPENAI_PROVIDERS.items()
        }

        env_gemini = (os.getenv("GEMINI_MODELS") or "").strip()
        self.gemini_models: List[str] = (
            [model.strip() for model in env_gemini.split(",") if model.strip()]
            if env_gemini
            else list(DEFAULT_GEMINI_MODELS)
        )
        self._gemini_models_verified = False

        env_creator = (os.getenv("CREATOR_ID") or "").strip()
        self.creator_ids: set[int] = {int(env_creator)} if env_creator.isdigit() else set()
        self._creator_fetched = False

        self._session: Optional[aiohttp.ClientSession] = None

        self.memory: Dict[int, deque] = {}
        self._memory_last_active: Dict[int, float] = {}
        self._ai_cfg_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
        self._channels_cache: Dict[int, Tuple[float, Tuple[List[str], List[str]]]] = {}
        self.rules_cache: Dict[int, Tuple[float, str]] = {}
        self._rates_cache: Optional[Tuple[float, str]] = None

        self.cooldowns: Dict[int, float] = {}
        self.cooldown_seconds = 3.0
        self._channel_auto_cooldowns: Dict[int, float] = {}
        self._dm_daily_usage: Dict[int, Tuple[str, int]] = {}
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
        last_active = self._memory_last_active.get(channel_id, 0.0)
        if last_active and now - last_active > MEMORY_TTL_SECONDS:
            self._clear_channel_memory(channel_id)

        if len(self.memory) > MAX_MEMORY_CHANNELS:
            expired = [
                channel
                for channel, timestamp in self._memory_last_active.items()
                if now - timestamp > MEMORY_TTL_SECONDS
            ]
            for channel in expired:
                self._clear_channel_memory(channel)

            if len(self.memory) > MAX_MEMORY_CHANNELS:
                oldest = sorted(
                    self._memory_last_active.items(), key=lambda item: item[1]
                )[: len(self.memory) // 5]
                for channel, _ in oldest:
                    self._clear_channel_memory(channel)

        self._memory_last_active[channel_id] = now
        return self.memory.setdefault(channel_id, deque(maxlen=15))

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET, limit=50, ttl_dns_cache=300
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    @commands.Cog.listener()
    async def on_ready(self):
        await self._verify_gemini_models()

    async def _verify_gemini_models(self):
        if self._gemini_models_verified or not self.gemini_key:
            return

        try:
            session = await self._get_session()
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": self.gemini_key}
            timeout = aiohttp.ClientTimeout(total=8)

            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    log.warning("Gemini ListModels вернул статус %s", response.status)
                    return

                data = await response.json()
                available = {
                    model.get("name", "").replace("models/", "")
                    for model in data.get("models") or []
                    if "generateContent" in (model.get("supportedGenerationMethods") or [])
                }
                filtered = [model for model in self.gemini_models if model in available]
                if filtered:
                    self.gemini_models = filtered
                    log.info(
                        "Подтверждённые модели Gemini: %s",
                        ", ".join(self.gemini_models),
                    )
                else:
                    log.warning(
                        "Gemini ListModels не подтвердил настроенные модели. "
                        "Сохраняем список из конфигурации."
                    )
                self._gemini_models_verified = True
        except Exception as error:
            log.warning("Не удалось проверить список моделей Gemini: %s", error)

    async def get_ai_config(self, guild_id: int) -> Dict[str, Any]:
        now = time.time()
        cached = self._ai_cfg_cache.get(guild_id)
        if cached and now - cached[0] < AI_CFG_CACHE_TTL:
            return cached[1]

        db_config = await api.get_guild_config(str(guild_id)) or {}
        ai = db_config.get("ai") or {}
        security = db_config.get("security") or {}
        config = {
            "aiEnabled": ai.get("enabled", True),
            "aiProvider": ai.get("provider") or "auto",
            "aiAutoReplyChance": int(ai.get("autoReplyChance") or 0),
            "aiCustomScenario": ai.get("customScenario"),
            "aiCustomRules": ai.get("customRules"),
            "logChannelId": db_config.get("logChannelId"),
            "verificationRoleId": security.get("verificationRoleId"),
            "trapChannelId": security.get("trapChannelId"),
        }

        if len(self._ai_cfg_cache) > MAX_RULES_CACHE_GUILDS:
            self._ai_cfg_cache = {
                key: value
                for key, value in self._ai_cfg_cache.items()
                if now - value[0] < AI_CFG_CACHE_TTL
            }

        self._ai_cfg_cache[guild_id] = (now, config)
        return config

    async def update_ai_config(self, guild_id: int, **kwargs) -> bool:
        current = dict(await self.get_ai_config(guild_id))
        current.update(kwargs)

        payload = {
            "enabled": current.get("aiEnabled", True),
            "provider": current.get("aiProvider") or "auto",
            "autoReplyChance": int(current.get("aiAutoReplyChance") or 0),
            "customScenario": current.get("aiCustomScenario"),
            "customRules": current.get("aiCustomRules"),
        }
        saved = await api.update_ai_config(str(guild_id), payload)
        if saved:
            self._ai_cfg_cache[guild_id] = (time.time(), current)
        return saved

    def _build_bot_capabilities(self, user_text: str) -> str:
        command_lines: List[str] = []
        short_names: List[str] = []

        for command in sorted(self.bot.slash_commands, key=lambda item: item.name):
            staff_only = bool(
                command.default_member_permissions
                and command.default_member_permissions.value != 0
            )
            tag = " [Персонал]" if staff_only else ""
            children = getattr(command, "children", None)
            if children:
                sub_names = ", ".join(sorted(children))
                short_names.append(f"/{command.name} ({sub_names})")
                for name, subcommand in sorted(children.items()):
                    description = getattr(subcommand, "description", "") or command.description
                    command_lines.append(f"• /{command.name} {name}{tag} — {description}")
            else:
                short_names.append(f"/{command.name}")
                command_lines.append(f"• /{command.name}{tag} — {command.description}")

        text = user_text.lower()
        need_details = any(
            word in text
            for word in (
                "команд", "умеешь", "можешь", "функц", "помог", "настро", "сдела",
                "как работает", "капч", "войс", "статист", "верифи", "роли", "роль",
                "ловуш", "лог", "аудит", "мут", "бан", "кик", "help", "stats", "ai",
            )
        )

        if not need_details:
            return f"\n[ТВОИ РЕАЛЬНЫЕ КОМАНДЫ: {', '.join(short_names)}]"

        mechanics = (
            "• Верификация: капча применяется к новым аккаунтам, если она включена. "
            "Роли могут восстанавливаться из базы.\n"
            "• Временные комнаты: при входе в канал-генератор создаётся комната "
            "с панелью управления. Когда комната пустеет, бот удаляет её.\n"
            "• Статистика: счётчики обновляются каждые 10 минут.\n"
            "• Канал-ловушка: бот удаляет сообщение и исключает участника."
        )
        return (
            "\n\n[ТВОИ РЕАЛЬНЫЕ КОМАНДЫ]:\n"
            + "\n".join(command_lines)
            + f"\n\nКак устроены модули:\n{mechanics}"
        )

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

    def _has_any_mod_permission(
        self, author: disnake.abc.User, guild: Optional[disnake.Guild]
    ) -> bool:
        if not guild or not isinstance(author, disnake.Member):
            return False
        if author.id == guild.owner_id or author.id in self.creator_ids:
            return True

        permissions = author.guild_permissions
        return any((
            permissions.administrator,
            permissions.moderate_members,
            permissions.kick_members,
            permissions.ban_members,
            permissions.manage_messages,
            permissions.manage_channels,
        ))

    async def _get_author_identity_tag(
        self, author: disnake.abc.User, guild: Optional[disnake.Guild]
    ) -> str:
        await self._ensure_creator_id()

        is_creator = author.id in self.creator_ids
        is_guild_owner = bool(guild and author.id == guild.owner_id)

        if is_creator and is_guild_owner:
            return (
                f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой создатель Disu (ID: {author.id}), "
                f"владелец сервера. Ник: «{author.display_name}».]"
            )
        if is_creator:
            return (
                f"⚡ [СИСТЕМНАЯ МЕТКА: Пишет твой создатель Disu (ID: {author.id}) "
                f"под ником «{author.display_name}».]"
            )
        if is_guild_owner:
            return (
                f"👑 [СИСТЕМНАЯ МЕТКА: Пишет владелец сервера "
                f"«{author.display_name}».]"
            )
        return ""

    @staticmethod
    def _parse_action_params(raw_params: str) -> Dict[str, str]:
        params: Dict[str, str] = {}
        for part in raw_params.split("|"):
            if "=" in part:
                name, value = part.split("=", 1)
                params[name.strip().lower()] = value.strip()
        return params

    def _can_moderate_target(
        self, guild: disnake.Guild, actor: disnake.Member, target: disnake.Member
    ) -> Optional[str]:
        if target.id == actor.id:
            return "нельзя применить действие к самому себе"
        if target.id == self.bot.user.id:
            return "нельзя применить действие ко мне"
        if target.id == guild.owner_id:
            return "нельзя применить действие к владельцу сервера"
        if actor.id != guild.owner_id and target.top_role >= actor.top_role:
            return "роль этого участника равна или выше твоей"
        if guild.me and target.top_role >= guild.me.top_role:
            return "роль этого участника равна или выше роли бота"
        return None

    async def _execute_ai_action(
        self,
        message: disnake.Message,
        ref_msg: Optional[disnake.Message],
        raw_action: str,
    ) -> Tuple[str, Optional[disnake.ui.View]]:
        guild = message.guild
        actor = message.author
        if guild is None or not isinstance(actor, disnake.Member):
            return "⚠️ Действия модерации доступны на сервере.", None

        action, _, raw_params = raw_action.partition("|")
        action = action.strip().lower()

        if action in {"timeout", "clear", "lock", "unlock", "slowmode"}:
            return f"Для этого действия используй команду `/{action}`.", None

        permission = {"kick": "kick_members", "ban": "ban_members"}.get(action)
        if permission is None:
            return "", None
        if not getattr(actor.guild_permissions, permission):
            return f"⛔ У тебя нет прав на `{action}`.", None

        allowed_ids: Set[int] = {member.id for member in message.mentions}
        if ref_msg:
            allowed_ids.add(ref_msg.author.id)
        allowed_ids.discard(self.bot.user.id)

        params = self._parse_action_params(raw_params)
        provided_id = params.get("user_id", "")
        if provided_id.isdecimal() and int(provided_id) in allowed_ids:
            target = guild.get_member(int(provided_id))
        elif not provided_id and len(allowed_ids) == 1:
            target = guild.get_member(next(iter(allowed_ids)))
        else:
            target = None

        if target is None:
            return "⚠️ Укажи участника упоминанием или ответь на его сообщение.", None

        if error := self._can_moderate_target(guild, actor, target):
            return f"⛔ Не могу выполнить: {error}.", None

        default_reason = "Заблокирован через Mirei" if action == "ban" else "Исключён через Mirei"
        reason = (params.get("reason") or default_reason)[:200]
        verb = "заблокировать" if action == "ban" else "исключить"
        view = ConfirmModActionView(actor.id, action, target, reason)
        text = (
            f"⚠️ Подтверди действие: **{verb}** участника **{target.display_name}** "
            f"(`{target.id}`)?\n*Причина: {reason}*"
        )
        return text, view

    @staticmethod
    def _extract_embeds_text(embeds: List[disnake.Embed]) -> str:
        if not embeds:
            return ""

        parts = []
        for index, embed in enumerate(embeds[:2], 1):
            items = []
            if embed.author and embed.author.name:
                items.append(f"Автор: {embed.author.name}")
            if embed.title:
                items.append(f"Заголовок: {embed.title}")
            if embed.description:
                items.append(f"Текст: {embed.description[:800]}")
            for field in embed.fields[:6]:
                items.append(f"{field.name}: {field.value[:200]}")
            if embed.footer and embed.footer.text:
                items.append(f"Подвал: {embed.footer.text}")
            if items:
                parts.append(f"[Вложение Embed #{index} -> " + " | ".join(items) + "]")
        return "\n".join(parts)

    @staticmethod
    def _extract_embed_image_url(embeds: List[disnake.Embed]) -> Optional[str]:
        for embed in embeds:
            if embed.image and embed.image.url:
                return embed.image.url
            if embed.thumbnail and embed.thumbnail.url:
                return embed.thumbnail.url
        return None

    async def _download_image_base64(
        self,
        attachment: Optional[disnake.Attachment] = None,
        image_url: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        url = attachment.url if attachment else image_url
        if not url:
            return None

        try:
            parsed = urllib.parse.urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc not in {"cdn.discordapp.com", "media.discordapp.net"}
                or not parsed.path.startswith("/attachments/")
            ):
                return None

            limit = 4 * 1024 * 1024
            if attachment and attachment.size > limit:
                return None

            session = await self._get_session()
            timeout = aiohttp.ClientTimeout(total=7)
            async with session.get(url, timeout=timeout, allow_redirects=False) as response:
                content_type = response.content_type.lower()
                if response.status != 200 or content_type not in ALLOWED_IMAGE_TYPES:
                    return None
                if response.content_length is not None and response.content_length > limit:
                    return None

                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if len(data) + len(chunk) > limit:
                        return None
                    data.extend(chunk)

                if data:
                    return content_type, base64.b64encode(data).decode("ascii")

        except (ValueError, aiohttp.ClientError, asyncio.TimeoutError):
            pass

        return None

    async def _get_server_rules_text(
        self, guild: disnake.Guild, cfg: Dict[str, Any]
    ) -> str:
        custom_rules = cfg.get("aiCustomRules")
        if custom_rules:
            return custom_rules[:1500]

        now = time.time()
        cached = self.rules_cache.get(guild.id)
        if cached and now - cached[0] < RULES_CACHE_TTL:
            return cached[1]

        if len(self.rules_cache) > MAX_RULES_CACHE_GUILDS:
            self.rules_cache = {
                key: value
                for key, value in self.rules_cache.items()
                if now - value[0] < RULES_CACHE_TTL
            }

        rules_channel = guild.rules_channel
        if not rules_channel:
            for channel in guild.text_channels:
                if any(word in channel.name.lower() for word in ("правил", "rules", "устав")):
                    rules_channel = channel
                    break

        if not rules_channel:
            text = "Канал правил не найден."
            self.rules_cache[guild.id] = (now, text)
            return text

        collected = []
        try:
            async for message in rules_channel.history(limit=5, oldest_first=True):
                if message.content:
                    collected.append(message.content[:1000])
                if message.embeds:
                    collected.append(self._extract_embeds_text(message.embeds))
        except disnake.HTTPException:
            pass

        rules = (
            "\n".join(collected)[:1500]
            if collected
            else f"Правила находятся в канале {rules_channel.mention}."
        )
        self.rules_cache[guild.id] = (now, rules)
        return rules

    def _get_public_channels_cached(
        self, guild: disnake.Guild, cfg: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        now = time.time()
        cached = self._channels_cache.get(guild.id)
        if cached and now - cached[0] < CHANNELS_CACHE_TTL:
            return cached[1]

        staff_keywords = (
            "админ", "адмен", "admin", "модер", "moder", "staff", "стафф",
            "логи", "logs", "audit", "аудит", "тикет", "ticket", "бан-лист", "руководств",
        )
        counter_keywords = (
            "all members", "members:", "bots:", "online:",
            "участников:", "онлайн:", "ботов:", "статистик", "stats",
        )
        log_channel_id = str(cfg.get("logChannelId") or "")

        verify_role: Optional[disnake.Role] = None
        verify_role_id = cfg.get("verificationRoleId")
        if verify_role_id and str(verify_role_id).isdigit():
            verify_role = guild.get_role(int(verify_role_id))

        if not verify_role:
            for role in guild.roles:
                if not role.is_default() and not role.managed and any(
                    word in role.name.lower()
                    for word in ("участник", "member", "verif", "игрок", "user")
                ):
                    verify_role = role
                    break

        check_roles = [guild.default_role]
        if verify_role:
            check_roles.append(verify_role)

        def is_staff_or_hidden_name(channel: disnake.abc.GuildChannel) -> bool:
            if str(channel.id) == log_channel_id:
                return True
            name = channel.name.lower()
            category = channel.category.name.lower() if channel.category else ""
            return any(word in name or word in category for word in staff_keywords)

        text_channels: List[str] = []
        for channel in guild.text_channels:
            if is_staff_or_hidden_name(channel):
                continue
            if any(channel.permissions_for(role).view_channel for role in check_roles):
                topic = f" ({channel.topic[:40]})" if channel.topic else ""
                age_tag = " [18+]" if channel.is_nsfw() else ""
                text_channels.append(f"<#{channel.id}> (#{channel.name}{age_tag}{topic})")
                if len(text_channels) >= 15:
                    break

        voice_channels: List[str] = []
        active_role = verify_role or guild.default_role
        for channel in guild.voice_channels:
            if is_staff_or_hidden_name(channel):
                continue

            name = channel.name.lower()
            if any(word in name for word in counter_keywords) or re.search(
                r"[:—\-]\s*\d+\s*$", channel.name
            ):
                continue

            permissions = channel.permissions_for(active_role)
            if permissions.view_channel and (permissions.connect or channel == guild.afk_channel):
                voice_channels.append(f"<#{channel.id}> (🔊 {channel.name})")
                if len(voice_channels) >= 10:
                    break

        if len(self._channels_cache) > MAX_RULES_CACHE_GUILDS:
            self._channels_cache = {
                key: value
                for key, value in self._channels_cache.items()
                if now - value[0] < CHANNELS_CACHE_TTL
            }

        result = (text_channels, voice_channels)
        self._channels_cache[guild.id] = (now, result)
        return result

    async def _build_guild_knowledge(
        self,
        guild: Optional[disnake.Guild],
        current_channel: disnake.abc.Messageable,
        cfg: Dict[str, Any],
    ) -> str:
        if not guild:
            return "Диалог идёт в личных сообщениях (DM). Твой создатель — Disu."

        owner = (
            f"{guild.owner.display_name} (<@{guild.owner.id}>)"
            if guild.owner
            else f"<@{guild.owner_id}>"
        )
        text_channels, voice_channels = self._get_public_channels_cached(guild, cfg)
        text_summary = ", ".join(text_channels) if text_channels else "Нет доступных"
        voice_summary = ", ".join(voice_channels) if voice_channels else "Нет доступных"
        rules = await self._get_server_rules_text(guild, cfg)
        channel_name = getattr(current_channel, "name", "ЛС")

        return (
            "\n--- ИНФОРМАЦИЯ О СЕРВЕРЕ ---\n"
            f"• Сервер: «{guild.name}» (Участников: {guild.member_count})\n"
            f"• Создатель бота: Disu | Владелец сервера: {owner}\n"
            f"• Текущий канал: <#{getattr(current_channel, 'id', 0)}> (#{channel_name})\n"
            f"• Текстовые каналы: {text_summary}\n"
            f"• Голосовые каналы: {voice_summary}\n"
            f"• Правила:\n{rules}\n"
            "----------------------------"
        )
    async def _fetch_weather(self, text: str) -> Optional[str]:
        clean = re.sub(
            r"\b(?:какая|какой|сейчас|сегодня|завтра|загугли|найди|скажи|покажи|"
            r"погода|погоду|градусов|температура|в|во|на)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        clean = re.sub(r"[^\w\s\-]", "", clean).strip()
        city_query = " ".join(clean.split()[:3]).strip()
        if len(city_query) < 2:
            city_query = "Москва"

        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=4)
        headers = {"User-Agent": "MireiDiscordBot/2.0"}
        latitude, longitude, place_name = None, None, city_query

        try:
            async with session.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": city_query,
                    "format": "json",
                    "limit": 1,
                    "accept-language": "ru",
                },
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status == 200:
                    results = await response.json()
                    if results:
                        result = results[0]
                        latitude = float(result["lat"])
                        longitude = float(result["lon"])
                        place_name = result.get("display_name", city_query).split(",")[0]
        except Exception:
            pass

        if latitude is None or longitude is None:
            candidates = [city_query]
            if len(city_query) > 4:
                stem = city_query[:-1]
                candidates.extend([stem, stem + "а", stem + "я"])

            for candidate in candidates:
                try:
                    async with session.get(
                        "https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": candidate, "count": 1, "language": "ru"},
                        timeout=timeout,
                    ) as response:
                        if response.status != 200:
                            continue

                        data = await response.json()
                        results = data.get("results") or []
                        if results:
                            result = results[0]
                            latitude = result["latitude"]
                            longitude = result["longitude"]
                            place_name = result.get("name", candidate)
                            break
                except Exception:
                    continue

        if latitude is None or longitude is None:
            return None

        try:
            async with session.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,apparent_temperature,relative_humidity_2m,"
                        "wind_speed_10m,weather_code"
                    ),
                    "timezone": "auto",
                },
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                current = data.get("current") or {}
                temperature = current.get("temperature_2m")
                if temperature is None:
                    return None

                description = WMO_WEATHER_CODES.get(
                    current.get("weather_code", 0), "Переменная облачность"
                )
                fields = [f"{description}, температура {temperature}°C"]
                if current.get("apparent_temperature") is not None:
                    fields.append(f"ощущается как {current['apparent_temperature']}°C")
                if current.get("wind_speed_10m") is not None:
                    fields.append(f"ветер {current['wind_speed_10m']} км/ч")
                if current.get("relative_humidity_2m") is not None:
                    fields.append(f"влажность {current['relative_humidity_2m']}%")

                return f"Погода в г. {place_name} прямо сейчас: {', '.join(fields)}."
        except Exception:
            return None

    async def _fetch_currency_rates(self) -> Optional[str]:
        now = time.time()
        if self._rates_cache and now - self._rates_cache[0] < RATES_CACHE_TTL_SECONDS:
            return self._rates_cache[1]

        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=4)

        async def get_cbr() -> Optional[str]:
            try:
                async with session.get(
                    "https://www.cbr-xml-daily.ru/daily_json.js", timeout=timeout
                ) as response:
                    if response.status != 200:
                        return None

                    data = json.loads(await response.text())
                    currencies = data.get("Valute") or {}
                    rates = []
                    for code in ("USD", "EUR", "CNY", "KZT"):
                        item = currencies.get(code) or {}
                        nominal = item.get("Nominal")
                        value = item.get("Value")
                        if nominal and value is not None:
                            rates.append(f"{nominal} {code} = {value:.2f} руб.")

                    return f"Курс ЦБ РФ: {', '.join(rates)}." if rates else None
            except Exception:
                return None

        async def get_crypto() -> Optional[str]:
            try:
                async with session.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={
                        "ids": "bitcoin,ethereum,the-open-network",
                        "vs_currencies": "usd,rub",
                    },
                    timeout=timeout,
                ) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()
                    rates = []
                    btc_usd = (data.get("bitcoin") or {}).get("usd")
                    if btc_usd is not None:
                        rates.append(f"BTC = ${btc_usd:,}")

                    ton = data.get("the-open-network") or {}
                    if ton.get("usd") is not None:
                        rate = f"TON = ${ton['usd']}"
                        if ton.get("rub") is not None:
                            rate += f" ({ton['rub']} руб.)"
                        rates.append(rate)

                    return f"Криптовалюты: {', '.join(rates)}." if rates else None
            except Exception:
                return None

        cbr, crypto = await asyncio.gather(get_cbr(), get_crypto())
        lines = [line for line in (cbr, crypto) if line]
        if not lines:
            return None

        result = "\n".join(lines)
        self._rates_cache = (now, result)
        return result

    async def _fetch_web_search(self, query: str) -> Optional[str]:
        clean_query = re.sub(
            r"\b(?:загугли|найди в интернете|найди в инете|найди|поищи|"
            r"расскажи про|что такое|кто такой)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if len(clean_query) < 2:
            clean_query = query
        clean_query = clean_query[:120]

        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=4)

        async def search_news() -> List[str]:
            results = []
            try:
                async with session.get(
                    "https://news.google.com/rss/search",
                    params={"q": clean_query, "hl": "ru", "gl": "RU", "ceid": "RU:ru"},
                    timeout=timeout,
                ) as response:
                    if response.status == 200:
                        xml = await response.text()
                        items = re.findall(
                            r"<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>.*?</item>",
                            xml,
                            flags=re.DOTALL,
                        )
                        for title, pub_date in items[:4]:
                            title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
                            results.append(f"• Новость ({pub_date[:16]}): {title}")
            except Exception:
                pass
            return results

        async def search_wiki() -> List[str]:
            results = []
            try:
                async with session.get(
                    "https://ru.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": clean_query,
                        "utf8": 1,
                        "format": "json",
                        "srlimit": 3,
                    },
                    headers={"User-Agent": "MireiDiscordBot/2.0"},
                    timeout=timeout,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get("query", {}).get("search", [])[:3]:
                            title = item.get("title", "")
                            snippet = html.unescape(
                                re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                            ).strip()
                            if snippet:
                                results.append(f"• Справка ({title}): {snippet}")
            except Exception:
                pass
            return results

        news, wiki = await asyncio.gather(search_news(), search_wiki())
        results = news + wiki
        return "\n".join(results) if results else None

    async def _gather_internet_context(self, raw_user_text: str) -> str:
        text = raw_user_text.lower()
        blocks = []

        weather_triggers = ("погод", "градус", "температур", "дождь в", "снег в", "метео")
        if any(word in text for word in weather_triggers):
            weather = await self._fetch_weather(raw_user_text)
            if weather:
                blocks.append(weather)

        currency_triggers = (
            "курс", "доллар", "евро", "рубл", "юан", "тенге",
            "биткоин", "btc", "крипт", "ton ",
        )
        if any(word in text for word in currency_triggers):
            rates = await self._fetch_currency_rates()
            if rates:
                blocks.append(rates)

        year = datetime.datetime.now().year
        search_triggers = (
            "загугли", "найди", "поищи", "новости", "когда выйдет",
            "когда вышел", "кто выиграл", "что случилось", "кто такой",
            "что такое", "актуальн", f"в {year}", f"в {year - 1}", f"в {year + 1}",
        )
        if not blocks and any(word in text for word in search_triggers):
            search = await self._fetch_web_search(raw_user_text)
            if search:
                blocks.append(search)

        if not blocks:
            return ""

        return "\n\n[ДАННЫЕ ИЗ ИНТЕРНЕТА В РЕАЛЬНОМ ВРЕМЕНИ]:\n" + "\n".join(blocks)

    async def _call_gemini(
        self,
        system_prompt: str,
        history: deque,
        current_msg: str,
        image_data: Optional[Tuple[str, str]],
    ) -> Optional[str]:
        if not self.gemini_key:
            return None

        if not self._gemini_models_verified:
            await self._verify_gemini_models()

        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in history
        ]
        user_parts: List[dict] = [{"text": current_msg}]
        if image_data:
            mime_type, image_base64 = image_data
            user_parts.append(
                {"inlineData": {"mimeType": mime_type, "data": image_base64}}
            )
        contents.append({"role": "user", "parts": user_parts})

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.gemini_key,
        }
        timeout = aiohttp.ClientTimeout(total=13 if image_data else 9)
        session = await self._get_session()

        for model in self.gemini_models:
            model_key = f"gemini:{model}"
            if not self._is_model_available(model_key):
                continue

            generation: Dict[str, Any] = {
                "temperature": 0.85,
                "maxOutputTokens": 800,
            }
            if "3.8" in model:
                generation["thinkingConfig"] = {"thinkingLevel": "low"}
            elif model.startswith("gemini-3"):
                generation["thinkingConfig"] = {"thinkingLevel": "minimal"}

            payload = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "safetySettings": SAFETY_SETTINGS_MODERATE,
                "generationConfig": generation,
            }
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent"
            )

            try:
                async with session.post(
                    url, json=payload, headers=headers, timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        candidates = data.get("candidates") or []
                        if not candidates:
                            return (
                                "🛡️ Ответ не получен. "
                                "Попробуй переформулировать запрос."
                            )

                        parts = (candidates[0].get("content") or {}).get("parts") or []
                        reply = "".join(
                            part.get("text", "")
                            for part in parts
                            if "text" in part and not part.get("thought")
                        ).strip()
                        if reply:
                            return reply

                    elif response.status == 404:
                        log.warning("Gemini: модель %s не найдена (404)", model)
                        self._ban_model(model_key, MODEL_COOLDOWN_NOT_FOUND)

                    else:
                        log.warning("Gemini: модель %s вернула HTTP %s", model, response.status)
                        self._ban_model(model_key, MODEL_COOLDOWN_TEMP)

            except asyncio.TimeoutError:
                log.warning("Таймаут Gemini: %s", model)
                self._ban_model(model_key, MODEL_COOLDOWN_TEMP)
            except Exception as error:
                log.warning("Сбой запроса Gemini %s: %s", model, error)
                self._ban_model(model_key, MODEL_COOLDOWN_TEMP)

        return None

    async def _call_openai_provider(
        self,
        provider_name: str,
        system_prompt: str,
        history: deque,
        current_msg: str,
    ) -> Optional[str]:
        provider = OPENAI_PROVIDERS.get(provider_name)
        api_key = self.provider_keys.get(provider_name)
        if not provider or not api_key:
            return None

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(
            {"role": message["role"], "content": message["content"]}
            for message in history
        )
        messages.append({"role": "user", "content": current_msg})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=9)

        for model in provider["models"]:
            model_key = f"{provider_name}:{model}"
            if not self._is_model_available(model_key):
                continue

            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": MAX_OUTPUT_TOKENS,
            }

            try:
                async with session.post(
                    provider["url"], json=payload, headers=headers, timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        choices = data.get("choices") or []
                        if choices:
                            message = choices[0].get("message") or {}
                            content = message.get("content")
                            if isinstance(content, str) and content.strip():
                                return content.strip()

                    elif response.status == 404:
                        log.warning("%s: модель %s не найдена (404)", provider_name, model)
                        self._ban_model(model_key, MODEL_COOLDOWN_NOT_FOUND)

                    else:
                        log.warning(
                            "%s: модель %s вернула HTTP %s",
                            provider_name, model, response.status,
                        )
                        self._ban_model(model_key, MODEL_COOLDOWN_TEMP)

            except asyncio.TimeoutError:
                log.warning("Таймаут %s: %s", provider_name, model)
                self._ban_model(model_key, MODEL_COOLDOWN_TEMP)
            except Exception as error:
                log.warning("Ошибка %s (%s): %s", provider_name, model, error)
                self._ban_model(model_key, MODEL_COOLDOWN_TEMP)

        return None

    async def _ask_llm_inner(
        self,
        guild: Optional[disnake.Guild],
        channel: disnake.abc.Messageable,
        author: disnake.abc.User,
        user_text: str,
        raw_user_text: str,
        attachment: Optional[disnake.Attachment],
        embed_img_url: Optional[str],
        is_spontaneous: bool,
    ) -> Optional[str]:
        channel_id = getattr(channel, "id", 0)
        history = self._get_channel_history(channel_id)
        config = await self.get_ai_config(guild.id) if guild else {}

        async def empty_none():
            return None

        async def empty_text():
            return ""

        knowledge_request = self._build_guild_knowledge(guild, channel, config)
        identity_request = self._get_author_identity_tag(author, guild)
        internet_request = (
            empty_text()
            if is_spontaneous
            else self._gather_internet_context(raw_user_text)
        )
        image_request = (
            self._download_image_base64(attachment, embed_img_url)
            if attachment or embed_img_url
            else empty_none()
        )

        guild_knowledge, identity, internet_context, image_data = await asyncio.gather(
            knowledge_request,
            identity_request,
            internet_request,
            image_request,
        )

        base_prompt = PROMPT_CHARACTER_BASE
        if not is_spontaneous and self._has_any_mod_permission(author, guild):
            base_prompt += PROMPT_MODERATION_ADDON

        scenario = config.get("aiCustomScenario")
        if scenario:
            base_prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ СЦЕНАРИЙ СЕРВЕРА:\n{scenario[:800]}"

        if is_spontaneous:
            base_prompt += (
                "\n\n[КОНТЕКСТ: Ты решила поддержать беседу без упоминания. "
                "Ответь в 1–2 предложениях и не используй теги ACTION.]"
            )

        capabilities = (
            "" if is_spontaneous else self._build_bot_capabilities(raw_user_text)
        )

        moscow_tz = datetime.timezone(datetime.timedelta(hours=3))
        now = datetime.datetime.now(moscow_tz)
        time_info = now.strftime(f"{WEEKDAYS_RU[now.weekday()]}, %d.%m.%Y, %H:%M (МСК)")

        system_prompt = (
            f"{base_prompt}\n"
            f"{guild_knowledge}"
            f"{capabilities}\n"
            f"Текущее время и дата: {time_info}."
            f"{internet_context}"
        )

        author_label = f"{author.display_name} (ID: {author.id})"
        current_message = (
            f"{identity}\n{author_label}: {user_text}"
            if identity
            else f"{author_label}: {user_text}"
        )

        providers: List[str] = []
        if self.gemini_key:
            providers.append("gemini")
        providers.extend(
            name for name in OPENAI_PROVIDERS if self.provider_keys.get(name)
        )

        preferred = config.get("aiProvider") or "auto"
        if preferred in providers:
            providers.remove(preferred)
            providers.insert(0, preferred)

        reply: Optional[str] = None
        for provider in providers:
            if provider == "gemini":
                reply = await self._call_gemini(
                    system_prompt, history, current_message, image_data
                )
            elif not image_data:
                reply = await self._call_openai_provider(
                    provider, system_prompt, history, current_message
                )
            if reply:
                break

        if not reply:
            return None

        if not is_spontaneous:
            suffix = " [Изображение]" if image_data else ""
            history.append(
                {"role": "user", "content": f"{author.display_name}: {user_text}{suffix}"}
            )

        history.append({"role": "assistant", "content": reply})
        self._memory_last_active[channel_id] = time.time()
        return reply

    async def _ask_llm(self, **kwargs) -> Optional[str]:
        try:
            return await asyncio.wait_for(
                self._ask_llm_inner(**kwargs), timeout=TOTAL_LLM_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.warning("Превышен общий таймаут ИИ (%s сек).", TOTAL_LLM_TIMEOUT)
            return None
    @staticmethod
    def _is_ignored_chat_channel(
        channel: disnake.abc.GuildChannel, guild: disnake.Guild
    ) -> bool:
        if guild.rules_channel and channel.id == guild.rules_channel.id:
            return True

        name = getattr(channel, "name", "").lower()
        ignored_words = (
            "правил", "rules", "логи", "logs", "audit", "аудит",
            "админ", "admin", "модер", "moder", "тикет", "ticket",
        )
        return any(word in name for word in ignored_words)

    def _check_dm_limit(self, user_id: int) -> bool:
        if user_id in self.creator_ids:
            return True

        today = datetime.date.today().isoformat()
        previous_day, count = self._dm_daily_usage.get(user_id, (today, 0))
        if previous_day != today:
            count = 0
        if count >= DM_DAILY_LIMIT:
            return False

        if len(self._dm_daily_usage) > 2000:
            self._dm_daily_usage = {
                key: value
                for key, value in self._dm_daily_usage.items()
                if value[0] == today
            }

        self._dm_daily_usage[user_id] = (today, count + 1)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        bot_user = self.bot.user
        if message.author.bot or bot_user is None:
            return

        guild = message.guild
        is_dm = guild is None
        is_spontaneous = False
        ref_msg: Optional[disnake.Message] = None
        now = time.time()

        if message.reference and message.reference.message_id:
            resolved = message.reference.resolved
            if isinstance(resolved, disnake.Message):
                ref_msg = resolved
            else:
                try:
                    ref_msg = await message.channel.fetch_message(
                        message.reference.message_id
                    )
                except disnake.HTTPException:
                    pass

        if is_dm:
            await self._ensure_creator_id()
            if not self._check_dm_limit(message.author.id):
                await message.reply(
                    f"⏳ Дневной лимит сообщений в ЛС исчерпан "
                    f"({DM_DAILY_LIMIT}/{DM_DAILY_LIMIT}). Приходи завтра!",
                    mention_author=False,
                    allowed_mentions=SAFE_MENTIONS,
                )
                return

        else:
            config = await self.get_ai_config(guild.id)
            trap_channel_id = config.get("trapChannelId")
            if trap_channel_id and str(message.channel.id) == str(trap_channel_id):
                return
            if config.get("aiEnabled", True) is False:
                return

            is_mentioned = bot_user in message.mentions
            is_reply_to_bot = ref_msg is not None and ref_msg.author.id == bot_user.id

            if not (is_mentioned or is_reply_to_bot):
                if (
                    not message.content
                    or message.content.startswith(("/", "!", "."))
                    or self._is_ignored_chat_channel(message.channel, guild)
                ):
                    return

                history = self._get_channel_history(message.channel.id)
                history.append(
                    {
                        "role": "user",
                        "content": f"{message.author.display_name}: {message.content[:400]}",
                    }
                )

                chance = int(config.get("aiAutoReplyChance") or 0)
                last_auto = self._channel_auto_cooldowns.get(message.channel.id, 0.0)
                if (
                    chance <= 0
                    or len(message.content.strip()) < 8
                    or now - last_auto < AUTO_REPLY_CHANNEL_COOLDOWN
                    or random.randint(1, 100) > chance
                ):
                    return

                is_spontaneous = True
                if len(self._channel_auto_cooldowns) > 2000:
                    self._channel_auto_cooldowns = {
                        channel_id: timestamp
                        for channel_id, timestamp in self._channel_auto_cooldowns.items()
                        if now - timestamp < AUTO_REPLY_CHANNEL_COOLDOWN
                    }
                self._channel_auto_cooldowns[message.channel.id] = now

        if not is_spontaneous:
            last_used = self.cooldowns.get(message.author.id, 0.0)
            if now - last_used < self.cooldown_seconds:
                return

            if len(self.cooldowns) > 2000:
                self.cooldowns = {
                    user_id: timestamp
                    for user_id, timestamp in self.cooldowns.items()
                    if now - timestamp < 60.0
                }
            self.cooldowns[message.author.id] = now

        raw_user_text = message.content
        for mention in (f"<@{bot_user.id}>", f"<@!{bot_user.id}>"):
            raw_user_text = raw_user_text.replace(mention, "")
        raw_user_text = raw_user_text.strip()

        clean_text = raw_user_text
        if message.embeds:
            embed_text = self._extract_embeds_text(message.embeds)
            if embed_text:
                clean_text = f"{clean_text}\n{embed_text}".strip()

        if ref_msg:
            quoted_parts = []
            if ref_msg.content:
                quoted_parts.append(ref_msg.content[:600])
            if ref_msg.embeds:
                quoted_parts.append(self._extract_embeds_text(ref_msg.embeds))

            if quoted_parts:
                quote = " | ".join(quoted_parts)
                clean_text = (
                    f"(В ответ на сообщение от {ref_msg.author.display_name} "
                    f"[ID: {ref_msg.author.id}]: «{quote}») {clean_text}"
                ).strip()

        attachment: Optional[disnake.Attachment] = None
        embed_image_url: Optional[str] = None

        if message.attachments:
            attachment = message.attachments[0]
        elif ref_msg and ref_msg.attachments:
            attachment = ref_msg.attachments[0]
        else:
            embed_image_url = self._extract_embed_image_url(message.embeds)
            if not embed_image_url and ref_msg:
                embed_image_url = self._extract_embed_image_url(ref_msg.embeds)

        if not clean_text:
            if not attachment and not embed_image_url:
                if not is_spontaneous:
                    await message.reply(
                        "💠 Я тут, чего звал?",
                        mention_author=False,
                        allowed_mentions=SAFE_MENTIONS,
                    )
                return

            clean_text = "Посмотри на это изображение и прокомментируй его!"
            raw_user_text = clean_text

        async with message.channel.typing():
            reply = await self._ask_llm(
                guild=guild,
                channel=message.channel,
                author=message.author,
                user_text=clean_text[:1500],
                raw_user_text=raw_user_text[:500],
                attachment=attachment,
                embed_img_url=embed_image_url,
                is_spontaneous=is_spontaneous,
            )

        if not reply:
            if not is_spontaneous:
                await message.reply(
                    "⚠️ Нейросеть временно недоступна. Попробуй чуть позже.",
                    mention_author=False,
                    allowed_mentions=SAFE_MENTIONS,
                )
            return

        reaction = re.search(r"\[REACT:\s*([^\]]+)\]", reply)
        if reaction:
            emoji = reaction.group(1).strip()
            reply = re.sub(r"\[REACT:\s*[^\]]+\]", "", reply).strip()
            if emoji:
                try:
                    await message.add_reaction(emoji)
                except (disnake.HTTPException, TypeError, ValueError):
                    pass

        action_status = ""
        confirm_view: Optional[disnake.ui.View] = None
        action = re.search(r"\[ACTION:\s*([^\]]+)\]", reply)
        if action:
            reply = re.sub(r"\[ACTION:\s*[^\]]+\]", "", reply).strip()
            if not is_spontaneous:
                action_status, confirm_view = await self._execute_ai_action(
                    message, ref_msg, action.group(1).strip()
                )

        if action_status:
            reply = f"{reply}\n\n{action_status}".strip()
        if not reply:
            return

        send_kwargs: Dict[str, Any] = {"allowed_mentions": SAFE_MENTIONS}
        if confirm_view is not None:
            send_kwargs["view"] = confirm_view

        try:
            await message.reply(reply[:2000], mention_author=False, **send_kwargs)
        except disnake.HTTPException:
            await message.channel.send(reply[:2000], **send_kwargs)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ai",
        description="Управление ИИ Mirei",
    )
    @commands.default_member_permissions(administrator=True)
    async def ai_control_panel(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model: Optional[str] = commands.Param(
            default=None,
            choices={
                "🔄 Авто-выбор": "auto",
                "✨ Google Gemini": "gemini",
                "⚡ Groq (Llama 3.3 70B)": "groq",
                "🌐 OpenRouter Free": "openrouter",
                "🌪️ Mistral AI": "mistral",
            },
            description="Предпочитаемый провайдер",
        ),
        auto_reply_chance: Optional[int] = commands.Param(
            default=None,
            description="Шанс случайного ответа в обычном чате",
            ge=0,
            le=100,
        ),
        enabled: Optional[bool] = commands.Param(
            default=None,
            description="Включить или выключить ИИ на сервере",
        ),
        reset_memory: bool = commands.Param(
            default=False,
            description="Очистить память диалога в текущем канале",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        await self._ensure_creator_id()
        if (
            not inter.author.guild_permissions.administrator
            and inter.author.id not in self.creator_ids
        ):
            await inter.edit_original_response(
                content="⛔ Управлять ИИ могут администраторы сервера."
            )
            return

        if model and model != "auto":
            has_key = self.gemini_key if model == "gemini" else self.provider_keys.get(model)
            if not has_key:
                await inter.edit_original_response(
                    content=f"⚠️ Для провайдера `{model}` отсутствует API-ключ в `.env`."
                )
                return

        updates: Dict[str, Any] = {}
        if model is not None:
            updates["aiProvider"] = model
        if auto_reply_chance is not None:
            updates["aiAutoReplyChance"] = auto_reply_chance
        if enabled is not None:
            updates["aiEnabled"] = enabled
        if reset_memory:
            self._clear_channel_memory(inter.channel_id)

        saved = not updates or await self.update_ai_config(inter.guild_id, **updates)
        config = await self.get_ai_config(inter.guild_id)
        view = AIControlPanelView(
            self, inter.author.id, inter.guild_id, inter.channel_id, config
        )
        embed = await view.build_embed(inter.guild)
        warning = None if saved else "⚠️ Не удалось сохранить настройки в БД."
        await inter.edit_original_response(content=warning, embed=embed, view=view)


def setup(bot: commands.Bot):
    bot.add_cog(AIChat(bot))