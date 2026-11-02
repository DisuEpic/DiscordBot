import os
import asyncio
import disnake
from disnake.ext import commands, tasks
from config import BOT_TOKEN, log
from api import api
from views import VerifyView

intents = disnake.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True


class AigisBot(commands.InteractionBot):
    async def close(self):
        await api.close()
        await super().close()


bot = AigisBot(intents=intents)

STATUS_ACTIVITIES = [
    disnake.Activity(type=disnake.ActivityType.watching, name="за порядком на Night Summer 🛡️"),
    disnake.Activity(type=disnake.ActivityType.playing, name="в чате | Тегни @Aigis 🤖"),
    disnake.Activity(type=disnake.ActivityType.listening, name="биение Папиллонного сердца ❤️"),
    disnake.Activity(type=disnake.ActivityType.watching, name="за голосовыми комнатами 🔊"),
]


@tasks.loop(seconds=45)
async def rotate_presence():
    for activity in STATUS_ACTIVITIES:
        await bot.change_presence(activity=activity)
        await asyncio.sleep(45)


@rotate_presence.before_loop
async def before_rotate_presence():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    if not rotate_presence.is_running():
        rotate_presence.start()

    print("==========================================")
    print(f"🤖 Aigis онлайн как: {bot.user} (ID: {bot.user.id})")
    print("🛡️ Модули активны. Защита периметра запущена.")
    print("==========================================")


@bot.event
async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception):
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


cogs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cogs")
for filename in os.listdir(cogs_dir):
    if filename.endswith(".py") and not filename.startswith("__"):
        bot.load_extension(f"cogs.{filename[:-3]}")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)