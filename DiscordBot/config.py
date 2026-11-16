import os
import logging
import disnake

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("mirei")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN в переменных окружения или .env файле.")

API_BASE_URL = os.getenv("API_BASE_URL") or "http://localhost:5298/api"
API_KEY = os.getenv("API_KEY", "")

VERIFY_TIMEOUT_MINUTES = 10
VERIFY_WINDOW_HOURS = 24

RAID_JOIN_THRESHOLD = 8
RAID_WINDOW_SECONDS = 20
RAID_ALERT_COOLDOWN = 300
YOUNG_ACCOUNT_DAYS = 3
CAPTCHA_ACCOUNT_DAYS = 7

UNIFIED_FOOTER = "Mirei • Умная защита и ИИ"

BRAND_COLOR = disnake.Color(0x00E5FF)     # Фирменный бирюзовый неон Mirei
ACCENT_PINK = disnake.Color(0xFF4D94)     # Неоновая сакура (акценты и Overdrive)
ACCENT_GOLD = disnake.Color(0xF59E0B)     # Янтарный золотой
COMBAT_RED = disnake.Color(0xE11D48)      # Рубиновый красный
TACTICAL_GREEN = disnake.Color(0x10B981)  # Изумрудный зеленый

GUILD_ONLY = disnake.InteractionContextTypes(guild=True)