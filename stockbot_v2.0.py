import pandas as pd
import time
import requests
import os
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

# ===== CREDENTIALS =====
# Rename .env.example to .env and fill in your keys
load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
API_KEY         = os.getenv("ALPACA_API_KEY")
SECRET_KEY      = os.getenv("ALPACA_SECRET_KEY")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client    = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# ===== DISCORD =====
def send_discord(msg):
    try:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": msg},
            timeout=10
        )
    except Exception as e:
        print("Discord error:", e)

# ===== CONFIG =====
SYMBOL = "AAPL"

START_BALANCE = 100000

PROFIT_TARGET = 0.008
STOP_LOSS = 0.005

RSI_BUY = 30

MIN_BARS_HOLD = 20

NO_BUY_AFTER = 15

FORCE_CLOSE_H = 15
FORCE_CLOSE_M = 45

# ===== STATE =====
balance = START_BALANCE
shares = 0
in_position = False
buy_price = 0
bars_held = 0

trades = []

market_open_sent = False
market_close_sent = False
daily_summary_sent = False

last_heartbeat_minute = -1

# ===== INDICATORS =====
def add_indicators(df):
    df = df.copy()

    df["ma_short"] = df["close"].rolling(5).mean()
    df["ma_long"] = df["close"].rolling(20).mean()

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (100 / (1 + rs))

    return df

# ===== GET DATA =====
def get_data():

    now_et = pd.Timestamp.now(tz="America/New_York")

    market_open_et = now_et.replace(
        hour=9,
        minute=30,
        second=0,
        microsecond=0
    )

    market_open_utc = market_open_et.tz_convert("UTC")

    request = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame.Minute,
        start=market_open_utc,
        feed=DataFeed.IEX
    )

    bars = data_client.get_stock_bars(request)

    df = bars.df

    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(SYMBOL, level="symbol")

    df = df.reset_index()

    df.columns = [c.lower() for c in df.columns]

    return df

# ===== SAFE FETCH =====
def get_data_safe():

    attempt = 1

    while True:
        try:
            return get_data()

        except Exception as e:

            print(f"Connection error (attempt {attempt}): {e}")

            send_discord(f"⚠️ DATA ERROR: {e}")

            attempt += 1

            time.sleep(30)

# ===== START =====
print("=" * 50)
print("AAPL LIVE BOT v2.0")
print("=" * 50)

send_discord("🚀 TRADING BOT STARTED")

# ===== MAIN LOOP =====
while True:

    try:

        now = pd.Timestamp.now(tz="America/New_York")

        # ===== RESET DAILY FLAGS =====
        if now.hour < 9:
            market_open_sent = False
            market_close_sent = False
            daily_summary_sent = False

        # ===== MARKET OPEN =====
        if (
            now.hour == 9 and
            now.minute >= 30 and
            not market_open_sent
        ):

            send_discord("🟢 MARKET OPEN")
            market_open_sent = True

        # ===== MARKET CLOSE =====
        if (
            now.hour == 16 and
            not market_close_sent
        ):

            send_discord("🔴 MARKET CLOSED")
            market_close_sent = True

        # ===== DAILY SUMMARY =====
        if (
            now.hour == 16 and
            now.minute >= 1 and
            not daily_summary_sent
        ):

            wins = [
                t for t in trades
                if t["action"] == "SELL" and t["pnl"] > 0
            ]

            losses = [
                t for t in trades
                if t["action"] == "SELL" and t["pnl"] <= 0
            ]

            total_pnl = balance - START_BALANCE

            summary = (
                f"📊 DAILY SUMMARY\n"
                f"Balance: ${balance:.2f}\n"
                f"PnL: ${total_pnl:+.2f}\n"
                f"Trades: {len(wins) + len(losses)}\n"
                f"Wins: {len(wins)} | Losses: {len(losses)}"
            )

            send_discord(summary)

            daily_summary_sent = True

        # ===== MARKET HOURS =====
        market_open = now.replace(
            hour=9,
            minute=30,
            second=0,
            microsecond=0
        )

        market_close = now.replace(
            hour=16,
            minute=0,
            second=0,
            microsecond=0
        )

        if now < market_open or now > market_close:

            print(
                f"Market closed. Current ET: "
                f"{now.strftime('%H:%M')}"
            )

            time.sleep(60)

            continue

        # ===== FETCH DATA =====
        df = get_data_safe()

        df = add_indicators(df)

        if len(df) < 20:
            print("Not enough bars yet...")
            time.sleep(60)
            continue

        last = df.iloc[-1]

        price = float(last["close"])

        bar_time = pd.to_datetime(
            last["timestamp"],
            utc=True
        ).tz_convert("America/New_York")

        # ===== STALE CHECK =====
        age = (now - bar_time).total_seconds()

        if age > 300:

            print(f"Stale data: {age:.0f}s old")

            send_discord(
                f"⚠️ STALE DATA: {age:.0f}s old"
            )

            time.sleep(30)

            continue

        # ===== HEARTBEAT =====
        if (
            now.minute % 15 == 0 and
            now.minute != last_heartbeat_minute
        ):

            send_discord(
                f"🟡 BOT ALIVE\n"
                f"{SYMBOL}: ${price:.2f}\n"
                f"RSI: {last['rsi']:.2f}"
            )

            last_heartbeat_minute = now.minute

        # ===== POSITION TRACKING =====
        if in_position:
            bars_held += 1

        # ===== CONSOLE =====
        print("\n====================")
        print(f"Time: {bar_time}")
        print(f"Price: ${price:.2f}")
        print(f"Balance: ${balance:.2f}")
        print(f"Shares: {shares}")
        print(f"RSI: {last['rsi']:.2f}")

        # ===== BUY =====
        if (
            not in_position and
            last["rsi"] < RSI_BUY and
            bar_time.hour < NO_BUY_AFTER
        ):

            shares = int(balance // price)

            if shares > 0:

                buy_price = price

                balance -= shares * price

                in_position = True

                bars_held = 0

                order = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=shares,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )

                trading_client.submit_order(order)

                trades.append({
                    "action": "BUY",
                    "price": price,
                    "shares": shares,
                    "time": bar_time
                })

                msg = (
                    f"🟢 BUY\n"
                    f"{shares} {SYMBOL}\n"
                    f"Price: ${price:.2f}\n"
                    f"RSI: {last['rsi']:.2f}"
                )

                print(msg)

                send_discord(msg)

        # ===== SELL =====
        elif (
            in_position and
            bars_held >= MIN_BARS_HOLD
        ):

            take_profit = (
                price >= buy_price * (1 + PROFIT_TARGET)
            )

            stop_loss = (
                price <= buy_price * (1 - STOP_LOSS)
            )

            force_close = (
                bar_time.hour == FORCE_CLOSE_H and
                bar_time.minute >= FORCE_CLOSE_M
            )

            if (
                take_profit or
                stop_loss or
                force_close
            ):

                balance += shares * price

                pnl = (
                    (price - buy_price) * shares
                )

                if take_profit:
                    reason = "TAKE PROFIT"

                elif stop_loss:
                    reason = "STOP LOSS"

                else:
                    reason = "FORCE CLOSE"

                order = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=shares,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )

                trading_client.submit_order(order)

                trades.append({
                    "action": "SELL",
                    "price": price,
                    "shares": shares,
                    "time": bar_time,
                    "pnl": pnl,
                    "reason": reason
                })

                msg = (
                    f"🔴 SELL\n"
                    f"{shares} {SYMBOL}\n"
                    f"Price: ${price:.2f}\n"
                    f"{reason}\n"
                    f"PnL: ${pnl:.2f}"
                )

                print(msg)

                send_discord(msg)

                shares = 0
                in_position = False
                bars_held = 0

        time.sleep(60)

    except KeyboardInterrupt:

        send_discord("🛑 BOT STOPPED MANUALLY")

        break

    except Exception as e:

        print("MAIN LOOP ERROR:", e)

        send_discord(f"🚨 MAIN LOOP ERROR:\n{e}")

        time.sleep(30)
