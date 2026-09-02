"""
Sends a daily Telegram message reminding you to take an umbrella
if rain is forecast in the next ~12 hours (4 x 3-hour OpenWeatherMap slots).

Designed to run under GitHub Actions (see weather_bot.yml), which handles
timing/timezone and injects secrets as environment variables.

Locally, the same environment variables are loaded from a .env file via
python-dotenv (see .env.example) — that file is git-ignored and never
pushed, so real secrets never touch the repo.

Required environment variables / GitHub Actions secrets:
  OWM_API_KEY          - OpenWeatherMap API key
  TELEGRAM_BOT_TOKEN   - Telegram bot token from BotFather
  TELEGRAM_CHAT_ID     - Your Telegram chat id
"""

import os
import sys

import requests
from dotenv import load_dotenv

# No-op on GitHub Actions (no .env file there); loads local secrets when
# running from your IDE / terminal. Does not override real env vars that
# are already set, so Actions' injected secrets always win if both exist.
load_dotenv()

OWM_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

MY_LAT = 59.923275
MY_LONG = 30.487188


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


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
    owm_key = get_env("OWM_API_KEY")
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")

    will_rain = check_rain(owm_key)
    message = "🌧️ Take an umbrella today!" if will_rain else "☀️ No rain expected today."

    send_telegram_message(bot_token, chat_id, message)
    print(f"Sent: {message}")


if __name__ == "__main__":
    main()