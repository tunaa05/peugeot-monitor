import os
from dotenv import load_dotenv

load_dotenv()

# Discord webhook URL
DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1439725920121389076/VpPM8C4yAAjHZu4LZUdrM0GEGVfvxMkhLkWn6OBeOkN_5AIfHhgVWRmlYnnktOm291Qa"
)

# Discord user ID for mentions (optional - leave empty to disable mentions)
# To find your Discord user ID: Enable Developer Mode in Discord settings, then right-click your name and "Copy ID"
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", "318472879799009281")

# Price range (monthly lease rate in euros)
# Handle empty strings from environment variables
_min_price = os.getenv("MIN_PRICE", "50")
_min_price = _min_price if _min_price and _min_price.strip() else "50"
MIN_PRICE = float(_min_price)

_max_price = os.getenv("MAX_PRICE", "200")
_max_price = _max_price if _max_price and _max_price.strip() else "200"
MAX_PRICE = float(_max_price)

# Yearly kilometer allowance (km per year)
_km_allowance = os.getenv("KM_ALLOWANCE", "15000")
_km_allowance = _km_allowance if _km_allowance and _km_allowance.strip() else "15000"
KM_ALLOWANCE = int(_km_allowance)

# Check interval in seconds (30 minutes = 1800 seconds)
_check_interval = os.getenv("CHECK_INTERVAL", "1800")
_check_interval = _check_interval if _check_interval and _check_interval.strip() else "1800"
CHECK_INTERVAL = int(_check_interval)

# Peugeot store URL with filters: 24 months / 15,000 km and 24 months / 20,000 km, max price 151€, radius 50km
STORE_URL = "https://financing.peugeot.store/bestand"

# Storage file for tracking seen offers
OFFERS_FILE = "offers.json"


