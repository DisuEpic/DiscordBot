import os
import logging
import asyncio

# Подключаем быстрый движок циклов событий uvloop на Linux/macOS
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

import disnake
from disnake.ext import commands, tasks
from config import BOT_TOKEN, log
from api import api
from views import VerifyView

# Настраиваемый параметр: уровень логирования сетевого шлюза Discord (WARNING скрывает лишний шум)
logging.getLogger("disnake.gateway").setLevel(logging.WARNING)

# Настройка прав (Intents) бота на получение событий от Discord
intents = disnake.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True


class MireiBot(commands.AutoShardedInteractionBot):
    async def close(self):
        # Корректно закрываем HTTP-сессию с C# API при остановке бота
        await api.close()
        await super().close()


# Явно создаём и назначаем цикл событий для Python 3.12+ до инициализации бота
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = MireiBot(intents=intents, loop=loop)


def _plural_servers(n: int) -> str:
    """Склоняет слово 'сервер' в зависимости от числа."""
    if 11 <= (n % 100) <= 19:
        return "серверов"
    last = n % 10
    if last == 1:
        return "сервер"
    if 2 <= last <= 4:
        return "сервера"
    return "серверов"


# Настраиваемый параметр: интервал обновления статуса бота в Discord (в минутах)
@tasks.loop(minutes=5)
async def rotate_presence():
    count = len(bot.guilds)
    count_str = f"{count:,}".replace(",", " ")
    activity = disnake.Activity(
        type=disnake.ActivityType.watching,
        name=f"{count_str} {_plural_servers(count)} | /инфо помощь"
    )
    await bot.change_presence(activity=activity)


@rotate_presence.before_loop
async def before_rotate_presence():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    # Регистрируем постоянные кнопки верификации, чтобы они работали после перезапуска
    bot.add_view(VerifyView(use_captcha=False))
    bot.add_view(VerifyView(use_captcha=True))
    if not rotate_presence.is_running():
        rotate_presence.start()

    print("==========================================")
    print(f"💠 Mirei онлайн как: {bot.user} (ID: {bot.user.id})")
    print(f"🛡️ Серверов под защитой: {len(bot.guilds)}. Модули активны.")
    print("==========================================")


@bot.event
async def on_slash_command_error(
    inter: disnake.ApplicationCommandInteraction, error: Exception
):
    if isinstance(error, commands.CommandInvokeError):
        error = error.original

    if isinstance(error, commands.MissingPermissions):
        msg = "⛔ У вас недостаточно прав для этой команды."
    elif isinstance(error, commands.CommandOnCooldown):
        msg = f"⏳ Команда на перезарядке. Повторите через {error.retry_after:.0f} сек."
    elif isinstance(error, commands.CheckFailure):
        msg = "⛔ Вы не можете использовать эту команду."
    else:
        cmd_name = inter.data.name if inter.data else "unknown"
        log.error("Ошибка в команде /%s", cmd_name, exc_info=error)
        msg = "❌ Произошла внутренняя ошибка. Администрация уведомлена, попробуйте позже."

    try:
        if inter.response.is_done():
            await inter.followup.send(msg, ephemeral=True)
        else:
            await inter.response.send_message(msg, ephemeral=True)
    except disnake.HTTPException:
        pass


# Автоматическая загрузка всех модулей (когов) из папки cogs/
cogs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cogs")
for filename in os.listdir(cogs_dir):
    if filename.endswith(".py") and not filename.startswith("__"):
        bot.load_extension(f"cogs.{filename[:-3]}")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)