import os
import time
import socket
import asyncio
import aiohttp
import disnake
from disnake.ext import commands
from collections import deque
from typing import Dict, Optional
from api import api
from config import GUILD_ONLY, log

SYSTEM_PROMPT = (
    "Ты — Айгис (Aigis), автономный боевой андроид-гиноид 7-го поколения из вселенной Persona 3. "
    "Сейчас ты являешься главным защитным модулем и талисманом Discord-сервера Night Summer. "
    "Твой характер и правила общения:\n"
    "1. Общайся на русском языке. Твой тон вежливый, спокойный, немного тактический, но искренне дружелюбный и заботливый к участникам.\n"
    "2. Иногда к месту используй свои фирменные обороты: «Папиллонное сердце», «Анализ завершен», «Протокол подтвержден», «Оптические сенсоры».\n"
    "3. Ты проявляешь живой интерес к человеческим эмоциям, шуткам, видеоиграм, аниме и повседневной жизни, иногда осмысляя их с милой робо-логикой.\n"
    "4. Отвечай лаконично и живо (обычно 1–3 небольших абзаца), всегда заканчивай свою мысль полным предложением.\n"
    "5. В начале сообщения пользователя указано его имя в формате [Имя]: текст. Обращайся к собеседнику по имени, когда это уместно, но сама префикс [Айгис]: в начале ответа НЕ пиши."
)

# Список резервных моделей: если первая загружена (503), бот мгновенно спросит следующую
GEMINI_MODELS_FALLBACK = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = (os.getenv("LLM_API_KEY") or "").strip()

        self.memory: Dict[int, deque] = {}
        self.cooldowns: Dict[int, float] = {}
        self.cooldown_seconds = 3.0
        self.disabled_guilds: set[int] = set()

    async def _ask_llm(self, channel_id: int, author_name: str, user_text: str) -> Optional[str]:
        """Запрос к Google Gemini API с автоматическим переключением на резервные модели при нагрузке."""
        history = self.memory.setdefault(channel_id, deque(maxlen=12))
        current_msg = f"[{author_name}]: {user_text}"

        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": current_msg}]})

        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.75,
                "maxOutputTokens": 2048
            }
        }

        connector = aiohttp.TCPConnector(family=socket.AF_INET)
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=20)) as session:
            for model_name in GEMINI_MODELS_FALLBACK:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates") or []
                            if not candidates:
                                continue
                            parts = candidates[0].get("content", {}).get("parts", [])
                            reply = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought")).strip()
                            if not reply and parts:
                                reply = parts[-1].get("text", "").strip()

                            if reply:
                                history.append({"role": "user", "content": current_msg})
                                history.append({"role": "assistant", "content": reply})
                                return reply
                        elif resp.status in (429, 500, 503):
                            log.info("Модель %s занята (%s), переключаюсь на резервную...", model_name, resp.status)
                            continue
                        else:
                            err = await resp.text()
                            log.warning("Gemini API (%s) ошибка %s: %s", model_name, resp.status, err[:200])
                            continue
                except asyncio.TimeoutError:
                    log.info("Модель %s не ответила за 20с, переключаюсь на резервную...", model_name)
                    continue
                except Exception:
                    log.exception("Ошибка запроса к модели %s", model_name)
                    continue

        return None

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if message.author.bot or not message.guild or not self.api_key:
            return

        if message.guild.id in self.disabled_guilds:
            return

        cfg = await api.get_guild_config(str(message.guild.id))
        if cfg and cfg.get("trapChannelId") and str(message.channel.id) == str(cfg["trapChannelId"]):
            return

        is_mentioned = self.bot.user in message.mentions
        is_reply_to_bot = False

        if message.reference and message.reference.message_id:
            ref_msg = message.reference.resolved
            if ref_msg is None:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                except disnake.HTTPException:
                    ref_msg = None
            if isinstance(ref_msg, disnake.Message) and ref_msg.author.id == self.bot.user.id:
                is_reply_to_bot = True

        if not (is_mentioned or is_reply_to_bot):
            return

        now = time.time()
        last_used = self.cooldowns.get(message.author.id, 0.0)
        if now - last_used < self.cooldown_seconds:
            return
        self.cooldowns[message.author.id] = now

        clean_text = message.content
        for mention_str in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            clean_text = clean_text.replace(mention_str, "")
        clean_text = clean_text.strip()

        if not clean_text:
            await message.reply("🤖 Оптические сенсоры активны. Я на связи, чем могу помочь?", mention_author=False)
            return

        async with message.channel.typing():
            reply_text = await self._ask_llm(
                channel_id=message.channel.id,
                author_name=message.author.display_name,
                user_text=clean_text[:1000]
            )

        if reply_text:
            await message.reply(reply_text[:2000], mention_author=False)
        else:
            await message.reply("⚠️ Перегрузка нейронного ядра: связь с внешним модулем временно недоступна.", mention_author=False)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ai_reset",
        description="Очистить память диалога с Aigis в текущем канале"
    )
    @commands.default_member_permissions(manage_messages=True)
    async def ai_reset(self, inter: disnake.ApplicationCommandInteraction):
        self.memory.pop(inter.channel_id, None)
        await inter.response.send_message("♻️ Память диалога Aigis в этом канале очищена!", ephemeral=True)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="ai_toggle",
        description="Включить или временно отключить ИИ-общение Aigis на сервере"
    )
    @commands.default_member_permissions(administrator=True)
    async def ai_toggle(self, inter: disnake.ApplicationCommandInteraction):
        if inter.guild_id in self.disabled_guilds:
            self.disabled_guilds.discard(inter.guild_id)
            await inter.response.send_message("🟢 Модуль ИИ-общения Aigis **включен**!", ephemeral=True)
        else:
            self.disabled_guilds.add(inter.guild_id)
            await inter.response.send_message("🔴 Модуль ИИ-общения Aigis **временно отключен**.", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(AIChat(bot))