"""
Sends a daily Telegram message reminding you to take an umbrella
if rain is forecast in the next ~12 hours (4 x 3-hour OpenWeatherMap slots).

Designed to run under GitHub Actions (see weather_bot.yml), which triggers
this script hourly during a window and lets it self-check the local time —
this keeps the 7:30 send time correct across DST changes without needing
to edit the cron schedule twice a year.

Required environment variables / GitHub Actions secrets:
  OWM_API_KEY          - OpenWeatherMap API key
  TELEGRAM_BOT_TOKEN   - Telegram bot token from BotFather
  TELEGRAM_CHAT_ID     - Your Telegram chat id
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

OWM_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

MY_LAT = 59.923275
MY_LONG = 30.487188

LOCAL_TZ = ZoneInfo("Europe/Warsaw")   # adjust if you're not in this timezone
TARGET_HOUR = 7
TARGET_MINUTE = 30
# Since this job is triggered roughly hourly, allow a window rather than
# an exact minute match, or it might never fire in that exact minute.
WINDOW_MINUTES = 30


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


def within_send_window() -> bool:
    now = datetime.now(LOCAL_TZ)
    target = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
    return abs((now - target).total_seconds()) <= WINDOW_MINUTES * 60


def check_rain(api_key: str) -> bool:
    params = {
        "lat": MY_LAT,
        "lon": MY_LONG,
        "appid": api_key,
        "cnt": 4,  # next ~12 hours, in 3-hour steps
    }
    response = requests.get(OWM_ENDPOINT, params=params, timeout=10)
    response.raise_for_status()
    weather_data = response.json()

    for forecast in weather_data["list"]:
        condition_code = forecast["weather"][0]["id"]
        if condition_code < 700:
            return True
    return False


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = TELEGRAM_API.format(token=token)
    response = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
    response.raise_for_status()


def main() -> None:
    if not within_send_window():
        print("Not within the send window yet, skipping this run.")
        return

    owm_key = get_env("OWM_API_KEY")
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")

    will_rain = check_rain(owm_key)
    message = "🌧️ Take an umbrella today!" if will_rain else "☀️ No rain expected today."

    send_telegram_message(bot_token, chat_id, message)
    print(f"Sent: {message}")


if __name__ == "__main__":
    main()