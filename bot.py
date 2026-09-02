"""
Telegram bot that lets any user /subscribe or /unsubscribe from a daily
umbrella-or-not forecast, sent every day at 7:30 (UTC+3).

Runs as a single always-on process: python-telegram-bot both listens for
commands (via polling) and schedules the daily broadcast (via its built-in
JobQueue) — no separate cron/Actions job needed.

Required environment variables:
  TELEGRAM_BOT_TOKEN   - Telegram bot token from BotFather
  OWM_API_KEY          - OpenWeatherMap API key

Locally these are loaded from a .env file via python-dotenv (git-ignored).
On the host (e.g. Fly.io), set them as real secrets/env vars instead.
"""

import json
import logging
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()  # no-op if there's no .env file (e.g. on the host)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUBSCRIBERS_FILE = Path(os.environ.get("SUBSCRIBERS_FILE_DIR", ".")) / "subscribers.json"

OWM_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"
MY_LAT = 59.923275
MY_LONG = 30.487188

UTC_PLUS_3 = timezone(timedelta(hours=3))
SEND_TIME = time(hour=7, minute=30, tzinfo=UTC_PLUS_3)

BTN_SUBSCRIBE = "🔔 Subscribe"
BTN_UNSUBSCRIBE = "🔕 Unsubscribe"
BTN_FORECAST = "☔ Forecast now"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_SUBSCRIBE, BTN_UNSUBSCRIBE], [BTN_FORECAST]],
    resize_keyboard=True,   # makes buttons a compact fixed size instead of huge
)


def load_subscribers() -> set[int]:
    if SUBSCRIBERS_FILE.exists():
        return set(json.loads(SUBSCRIBERS_FILE.read_text()))
    return set()


def save_subscribers(subscribers: set[int]) -> None:
    SUBSCRIBERS_FILE.write_text(json.dumps(sorted(subscribers)))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I can send you a daily umbrella-or-not forecast at 7:30.\n\n"
        "Use the buttons below.",
        reply_markup=MAIN_KEYBOARD,
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subscribers = load_subscribers()
    if chat_id in subscribers:
        await update.message.reply_text("You're already subscribed.")
        return
    subscribers.add(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text("Subscribed! You'll get a forecast every day at 7:30.")


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subscribers = load_subscribers()
    if chat_id not in subscribers:
        await update.message.reply_text("You're not subscribed.")
        return
    subscribers.discard(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text("Unsubscribed — you won't get any more forecasts.")


def build_forecast_message(api_key: str) -> str:
    params = {
        "lat": MY_LAT,
        "lon": MY_LONG,
        "appid": api_key,
        "units": "metric",  # so temps come back in °C instead of Kelvin
        "cnt": 4,  # next ~12 hours, in 3-hour steps
    }
    response = requests.get(OWM_ENDPOINT, params=params, timeout=10)
    response.raise_for_status()
    weather_data = response.json()

    will_rain = any(f["weather"][0]["id"] < 700 for f in weather_data["list"])
    header = "🌧️ Take an umbrella today!" if will_rain else "☀️ No rain expected today."

    lines = [header, ""]
    for forecast in weather_data["list"]:
        # "dt" is a Unix timestamp in UTC; convert to UTC+3 for display
        slot_time = datetime.fromtimestamp(forecast["dt"], tz=UTC_PLUS_3)
        temp = forecast["main"]["temp"]
        feels_like = forecast["main"]["feels_like"]
        condition_code = forecast["weather"][0]["id"]
        icon = "🌧️" if condition_code < 700 else "☀️"
        lines.append(
            f"{slot_time.strftime('%H:%M')} {icon} {temp:.0f}°C (feels like {feels_like:.0f}°C)"
        )

    return "\n".join(lines)


async def send_daily_forecast(context: ContextTypes.DEFAULT_TYPE) -> None:
    subscribers = load_subscribers()
    if not subscribers:
        logger.info("No subscribers, skipping today's send.")
        return

    owm_key = os.environ["OWM_API_KEY"]
    message = build_forecast_message(owm_key)

    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            logger.warning(f"Failed to send to {chat_id}: {exc}")


async def forecast_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger the same broadcast job the daily schedule uses,
    for testing. Sends to all current subscribers, same as the real run."""
    await update.message.reply_text("Triggering forecast now...")
    await send_daily_forecast(context)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe))
    application.add_handler(CommandHandler("forecast", forecast_now))

    # Same handlers, triggered by tapping a reply-keyboard button instead
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_SUBSCRIBE}$"), subscribe))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_UNSUBSCRIBE}$"), unsubscribe))
    application.add_handler(MessageHandler(filters.Regex(f"^{BTN_FORECAST}$"), forecast_now))

    application.job_queue.run_daily(send_daily_forecast, time=SEND_TIME)

    logger.info("Bot starting (polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()