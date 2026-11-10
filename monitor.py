
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

API_URL = (
    "https://fapi.binance.com/fapi/v1/klines"
    "?symbol=BTCUSDT&interval=5m&limit=1000"
)

STATE_FILE = Path("state.json")


def send_notification(message, priority="default"):
    topic = os.environ.get("NTFY_TOPIC", "").strip()

    if not topic:
        raise RuntimeError("Missing GitHub Secret: NTFY_TOPIC")

    if topic.startswith("http") or "/" in topic:
        raise RuntimeError(
            "NTFY_TOPIC must contain only the topic name"
        )

    url = "https://ntfy.sh/" + urllib.parse.quote(topic)

    request = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "BTCUSDT MA137 / MA700",
            "Priority": priority,
            "Tags": "chart_with_upwards_trend"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError("ntfy notification failed")

    print("Notification sent successfully")


def fetch_candles():
    request = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "BTC-MA-Alert/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(
            f"Binance API HTTP {error.code}: {detail}"
        )

    except Exception as error:
        raise RuntimeError(f"Binance connection failed: {error}")

    now = int(time.time() * 1000)

    # Only use fully closed 5-minute candles
    closed = [
        candle for candle in data
        if int(candle[6]) < now
    ]

    if len(closed) < 701:
        raise RuntimeError("Not enough closed candles")

    return closed


def sma(values):
    return sum(values) / len(values)


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, indent=2) + "\n"
    )


def main():
    # Optional manual test notification
    if os.environ.get("SEND_TEST_NOTIFICATION", "").lower() in (
        "true", "1", "yes"
    ):
        send_notification(
            "Test successful! Your BTCUSDT MA137/700 "
            "iPhone notification is connected."
        )

    candles = fetch_candles()

    closes = [float(candle[4]) for candle in candles]

    # Current closed candle and previous closed candle
    ma137_now = sma(closes[-137:])
    ma700_now = sma(closes[-700:])

    ma137_previous = sma(closes[-138:-1])
    ma700_previous = sma(closes[-701:-1])

    last_candle = candles[-1]
    candle_time = int(last_candle[0])
    price = float(last_candle[4])

    print("Binance API connected successfully")
    print("BTCUSDT:", price)
    print("MA137:", ma137_now)
    print("MA700:", ma700_now)
    print("Closed candle:", candle_time)

    cross_down = (
        ma137_previous >= ma700_previous
        and ma137_now < ma700_now
    )

    cross_up = (
        ma137_previous <= ma700_previous
        and ma137_now > ma700_now
    )

    state = load_state()

    if cross_down or cross_up:
        if state.get("last_alert_open_time") == candle_time:
            print("Duplicate signal skipped")
            return

        if cross_down:
            direction = "DOWN"
            message = (
                "🔴 MA137 跌破 MA700\n"
                "BTCUSDT Perpetual\n"
                "5分钟K线收盘确认\n\n"
                f"BTC Price: {price:.2f}\n"
                f"MA137: {ma137_now:.2f}\n"
                f"MA700: {ma700_now:.2f}"
            )
            priority = "high"

        else:
            direction = "UP"
            message = (
                "🟢 MA137 突破 MA700\n"
                "BTCUSDT Perpetual\n"
                "5分钟K线收盘确认\n\n"
                f"BTC Price: {price:.2f}\n"
                f"MA137: {ma137_now:.2f}\n"
                f"MA700: {ma700_now:.2f}"
            )
            priority = "high"

        send_notification(message, priority)

        state["last_alert_open_time"] = candle_time
        state["last_alert_direction"] = direction
        save_state(state)

        print("Signal:", direction)

    else:
        print("No MA137 / MA700 crossover")


if __name__ == "__main__":
    main()
