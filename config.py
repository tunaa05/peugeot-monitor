import os
from dotenv import load_dotenv

load_dotenv()

# Discord webhook URL
DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1439725920121389076/VpPM8C4yAAjHZu4LZUdrM0GEGVfvxMkhLkWn6OBeOkN_5AIfHhgVWRmlYnnktOm291Qa"
)

# Price range (monthly lease rate in euros)
# Handle empty strings from environment variables
_min_price = os.getenv("MIN_PRICE", "50")
_min_price = _min_price if _min_price and _min_price.strip() else "50"
MIN_PRICE = float(_min_price)

_max_price = os.getenv("MAX_PRICE", "120")
_max_price = _max_price if _max_price and _max_price.strip() else "120"
MAX_PRICE = float(_max_price)

# Yearly kilometer allowance (km per year)
_km_allowance = os.getenv("KM_ALLOWANCE", "15000")
_km_allowance = _km_allowance if _km_allowance and _km_allowance.strip() else "15000"
KM_ALLOWANCE = int(_km_allowance)

# Check interval in seconds (30 minutes = 1800 seconds)
_check_interval = os.getenv("CHECK_INTERVAL", "1800")
_check_interval = _check_interval if _check_interval and _check_interval.strip() else "1800"
CHECK_INTERVAL = int(_check_interval)

# Peugeot store URL
STORE_URL = "https://financing.peugeot.store/bestand"

# Storage file for tracking seen offers
OFFERS_FILE = "offers.json"
