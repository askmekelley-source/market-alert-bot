import requests
import pandas as pd
import yfinance as yf
import websocket, json
from datetime import datetime
import ta
import threading
import time
from config import (
from config import DISCORD_WEBHOOK
import requests
from datetime import datetime

def test_alert():
    requests.post(
        DISCORD_WEBHOOK,
        json={
            "username": "Market Alerts Bot",
            "content": f"✅ Bot is online and sending messages! {datetime.utcnow().strftime('%H:%M:%S UTC')}"
        }
    )

test_alert(yolo bolo)

    DISCORD_WEBHOOK,
    STOCKS,
    CRYPTO,
    CONFIDENCE_THRESHOLD,
    ATR_MULTIPLIER,
    TAKE_PROFIT_RR,
)

# ----------------------
# DISCORD EMBED
# ----------------------
def send_embed(asset, direction, confidence, price, entry, stop, target, reasons, market_type):
    color = 3066993 if direction == "BUY" else 15158332

    embed = {
        "title": f"{direction} SIGNAL • {confidence}%",
        "color": color,
        "fields": [
            {"name": "Asset", "value": asset, "inline": True},
            {"name": "Market", "value": market_type, "inline": True},
            {"name": "Confidence", "value": f"{confidence}%", "inline": True},
            {"name": "Entry", "value": f"${entry}", "inline": True},
            {"name": "Stop Loss", "value": f"${stop}", "inline": True},
            {"name": "Target", "value": f"${target}", "inline": True},
            {"name": "Current Price", "value": f"${price}", "inline": True},
            {
                "name": "Signal Breakdown",
                "value": "\n".join(f"• {r}" for r in reasons),
                "inline": False,
            },
        ],
        "footer": {
            "text": f"Market Alerts Bot • {datetime.utcnow().strftime('%H:%M:%S UTC')}"
        },
    }

    requests.post(DISCORD_WEBHOOK, json={"username": "Market Alerts Bot", "embeds": [embed]})


# ----------------------
# INDICATORS
# ----------------------
def apply_indicators(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema_fast"] = ta.trend.EMAIndicator(df["close"], 9).ema_indicator()
    df["ema_slow"] = ta.trend.EMAIndicator(df["close"], 21).ema_indicator()
    df["atr"] = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"]
    ).average_true_range()
    return df


def score_signal(df):
    latest = df.iloc[-1]
    score = 0
    reasons = []
    direction = None

    if latest["rsi"] < 30:
        score += 25
        reasons.append("RSI oversold")
    elif latest["rsi"] > 70:
        score += 25
        reasons.append("RSI overbought")

    if latest["ema_fast"] > latest["ema_slow"]:
        score += 25
        reasons.append("Bullish EMA trend")
        direction = "BUY"
    elif latest["ema_fast"] < latest["ema_slow"]:
        score += 25
        reasons.append("Bearish EMA trend")
        direction = "SELL"

    return direction, score, reasons


def timeframe_bias(df):
    df = apply_indicators(df)
    latest = df.iloc[-1]
    if latest["ema_fast"] > latest["ema_slow"]:
        return "BULL"
    if latest["ema_fast"] < latest["ema_slow"]:
        return "BEAR"
    return "NEUTRAL"


def calculate_entry_stop_target(df, direction):
    price = df.iloc[-1]["close"]
    atr = df.iloc[-1]["atr"]

    if direction == "BUY":
        entry = price
        stop = price - ATR_MULTIPLIER * atr
        target = entry + (entry - stop) * TAKE_PROFIT_RR
    else:
        entry = price
        stop = price + ATR_MULTIPLIER * atr
        target = entry - (stop - entry) * TAKE_PROFIT_RR

    return round(entry, 2), round(stop, 2), round(target, 2)


# ----------------------
# STOCK CHECK
# ----------------------
def check_stock(symbol):
    try:
        df_1m = yf.download(symbol, interval="1m", period="1d")
        df_5m = yf.download(symbol, interval="5m", period="5d")
        df_15m = yf.download(symbol, interval="15m", period="5d")

        for df in [df_1m, df_5m, df_15m]:
            df.rename(
                columns={"Close": "close", "High": "high", "Low": "low"},
                inplace=True,
            )

        df_1m = apply_indicators(df_1m)
        direction, score, reasons = score_signal(df_1m)

        if direction:
            bias_5m = timeframe_bias(df_5m)
            bias_15m = timeframe_bias(df_15m)

            if (
                direction == "BUY"
                and bias_5m == "BULL"
                and bias_15m == "BULL"
            ) or (
                direction == "SELL"
                and bias_5m == "BEAR"
                and bias_15m == "BEAR"
            ):
                score += 30
                reasons.append("5m & 15m confirmation")

            if score >= CONFIDENCE_THRESHOLD:
                entry, stop, target = calculate_entry_stop_target(df_1m, direction)
                price = round(df_1m.iloc[-1]["close"], 2)

                send_embed(
                    symbol,
                    direction,
                    score,
                    price,
                    entry,
                    stop,
                    target,
                    reasons,
                    "STOCK",
                )

    except Exception as e:
        print(f"Stock error ({symbol}):", e)


# ----------------------
# CRYPTO STREAM (BINANCE)
# ----------------------
prices = []


def on_message(ws, message):
    global prices
    data = json.loads(message)
    k = data["k"]

    prices.append(
        {
            "close": float(k["c"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
        }
    )

    if len(prices) < 30:
        return

    df = pd.DataFrame(prices[-30:])
    df = apply_indicators(df)
    direction, score, reasons = score_signal(df)

    if direction:
        df_5m = df.iloc[::5]
        df_15m = df.iloc[::15]

        if (
            direction == "BUY"
            and timeframe_bias(df_5m) == "BULL"
            and timeframe_bias(df_15m) == "BULL"
        ) or (
            direction == "SELL"
            and timeframe_bias(df_5m) == "BEAR"
            and timeframe_bias(df_15m) == "BEAR"
        ):
            score += 30
            reasons.append("5m & 15m confirmation")

        if score >= CONFIDENCE_THRESHOLD:
            entry, stop, target = calculate_entry_stop_target(df, direction)

            send_embed(
                "BTC/USDT",
                direction,
                score,
                df.iloc[-1]["close"],
                entry,
                stop,
                target,
                reasons,
                "CRYPTO",
            )


def start_crypto():
    socket = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    ws = websocket.WebSocketApp(socket, on_message=on_message)
    ws.run_forever()


# ----------------------
# MAIN
# ----------------------
if __name__ == "__main__":
    threading.Thread(target=start_crypto).start()

    while True:
        for stock in STOCKS:
            check_stock(stock)
        time.sleep(60)
