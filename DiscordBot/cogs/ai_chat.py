import os
import time
import aiohttp
import disnake
from disnake.ext import commands
from collections import deque
from typing import Dict, List, Optional
from api import api
from config import GUILD_ONLY, log

# Инструкция личности для нейросети (Характер Aigis)
SYSTEM_PROMPT = (
    "Ты — Айгис (Aigis), автономный боевой андроид-гиноид 7-го поколения из вселенной Persona 3. "
    "Сейчас ты являешься главным защитным модулем и талисманом Discord-сервера Night Summer. "
    "Твой характер и правила общения:\n"
    "1. Общайся на русском языке. Твой тон вежливый, спокойный, немного тактический, но искренне дружелюбный и заботливый к участникам.\n"
    "2. Иногда к месту используй свои фирменные обороты: «Папиллонное сердце», «Анализ завершен», «Протокол подтвержден», «Оптические сенсоры».\n"
    "3. Ты проявляешь живой интерес к человеческим эмоциям, шуткам, видеоиграм, аниме и повседневной жизни, иногда осмысляя их с милой робо-логикой.\n"
    "4. Отвечай лаконично и живо (обычно 1–3 небольших абзаца), как в обычном чате Discord. Не пиши огромные скучные простыни текста.\n"
    "5. В начале сообщения пользователя указано его имя в формате [Имя]: текст. Обращайся к собеседнику по имени, когда это уместно, но сама префикс [Айгис]: в начале ответа НЕ пиши."
)


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Берем ключ нейросети из переменных окружения (.env)
        self.api_key = (os.getenv("LLM_API_KEY") or "").strip()
        self.custom_model = (os.getenv("LLM_MODEL") or "").strip()

        # Память диалогов по каналам: {channel_id: deque([...])}
        self.memory: Dict[int, deque] = {}
        # Защита от спама (кулдаун 4 сек на участника): {user_id: timestamp}
        self.cooldowns: Dict[int, float] = {}
        self.cooldown_seconds = 4.0
        # Список серверов, где админ временно выключил ИИ командой /ai_toggle
        self.disabled_guilds: set[int] = set()

    def _get_provider_config(self) -> tuple[str, str]:
        """Определяет по началу ключа, какой сервис используется: Google Gemini или Groq."""
        if self.api_key.startswith(("AIza", "AQ.")):
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            default_model = "gemini-3.8-flash"
        elif self.api_key.startswith("gsk_"):
            url = "https://api.groq.com/openai/v1/chat/completions"
            default_model = "llama-3.3-70b-versatile"
        else:
            url = os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1/chat/completions"
            default_model = "deepseek/deepseek-chat"

        return url, (self.custom_model or default_model)

    async def _ask_llm(self, channel_id: int, author_name: str, user_text: str) -> Optional[str]:
        """Отправляет историю диалога и новое сообщение в нейросеть и возвращает ответ."""
        url, model_name = self._get_provider_config()
        history = self.memory.setdefault(channel_id, deque(maxlen=12))

        # Собираем цепочку: Системный промпт + История канала + Текущий вопрос
        messages_payload: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *list(history),
            {"role": "user", "content": f"[{author_name}]: {user_text}"}
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model_name,
            "messages": messages_payload,
            "temperature": 0.75,
            "max_tokens": 500
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data["choices"][0]["message"]["content"].strip()
                        # Сохраняем вопрос и ответ в память канала
                        history.append({"role": "user", "content": f"[{author_name}]: {user_text}"})
                        history.append({"role": "assistant", "content": reply})
                        return reply
                    else:
                        err_text = await resp.text()
                        log.warning("LLM API ошибка %s: %s", resp.status, err_text[:300])
                        return None
        except Exception:
            log.exception("Не удалось выполнить запрос к LLM API")
            return None

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        # 1. Игнорируем ботов, ЛС и случаи, когда ключ не задан в .env
        if message.author.bot or not message.guild or not self.api_key:
            return

        if message.guild.id in self.disabled_guilds:
            return

        # 2. Не отвечаем в канале-ловушке
        cfg = await api.get_guild_config(str(message.guild.id))
        if cfg and cfg.get("trapChannelId") and str(message.channel.id) == str(cfg["trapChannelId"]):
            return

        # 3. Проверяем триггер: тегнули @Aigis ИЛИ ответили (Reply) на её сообщение
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

        # 4. Проверяем кулдаун (не чаще 1 раза в 4 секунды от одного человека)
        now = time.time()
        last_used = self.cooldowns.get(message.author.id, 0.0)
        if now - last_used < self.cooldown_seconds:
            return
        self.cooldowns[message.author.id] = now

        # 5. Вырезаем само упоминание <@ID_бота> из текста сообщения
        clean_text = message.content
        for mention_str in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            clean_text = clean_text.replace(mention_str, "")
        clean_text = clean_text.strip()

        # Если человека просто пинганул бота пустым сообщением "@Aigis"
        if not clean_text:
            await message.reply("🤖 Оптические сенсоры активны. Я на связи, чем могу помочь?", mention_author=False)
            return

        # 6. Включаем анимацию "Aigis печатает..." и запрашиваем ответ у ИИ
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