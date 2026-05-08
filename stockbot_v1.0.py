import pandas as pd
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

# ===== API KEYS =====
# Rename .env.example to .env and add your keys there
import os
from dotenv import load_dotenv
load_dotenv()

API_KEY    = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client    = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# ===== CONFIG =====
SYMBOL        = "AAPL"
START_BALANCE = 100000
PROFIT_TARGET = 0.008
STOP_LOSS     = 0.007   # tighter than v1.01 (0.005)
RSI_BUY       = 30
MIN_BARS_HOLD = 20
NO_BUY_AFTER  = 15
FORCE_CLOSE_H = 15
FORCE_CLOSE_M = 45

balance     = START_BALANCE
shares      = 0
in_position = False
buy_price   = 0
bars_held   = 0
trades      = []

# ===== INDICATORS =====
def add_indicators(df):
    df = df.copy()
    df["ma_short"] = df["close"].rolling(5).mean()
    df["ma_long"]  = df["close"].rolling(20).mean()

    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    rs    = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    return df

# ===== GET DATA =====
def get_data():
    now = pd.Timestamp.now(tz="America/New_York")
    today_open = now.replace(hour=9, minute=30, second=0, microsecond=0).tz_convert("UTC")

    request = StockBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame.Minute,
        start=today_open,
        feed=DataFeed.IEX
    )
    bars = data_client.get_stock_bars(request)
    df   = bars.df

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
            print(f"  Connection error (attempt {attempt}): {e}")
            print(f"  Retrying in 30 seconds...")
            attempt += 1
            time.sleep(30)

# ===== START =====
print("=" * 50)
print("  AAPL LIVE BOT v1.0")
print(f"  TP: {PROFIT_TARGET*100}%  SL: {STOP_LOSS*100}%  RSI: {RSI_BUY}  HOLD: {MIN_BARS_HOLD} bars")
print("  Runs 9:30am - 3:45pm ET")
print("  Press Ctrl+C to stop")
print("=" * 50)

while True:
    try:
        now = pd.Timestamp.now(tz="America/New_York")

        market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)

        if now < market_open or now > market_close:
            print(f"  Market closed. Current ET: {now.strftime('%H:%M')}  Waiting...")
            time.sleep(60)
            continue

        df = get_data_safe()
        df = add_indicators(df)

        last     = df.iloc[-1]
        price    = float(last["close"])
        bar_time = pd.Timestamp(last["timestamp"]).tz_convert("America/New_York")

        age = (now - bar_time).total_seconds()
        if age > 300:
            print(f"  Stale data ({age:.0f}s old), waiting...")
            time.sleep(30)
            continue

        if in_position:
            bars_held += 1

        print("\n====================")
        print(f"Time:     {bar_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"Price:    ${price:.2f}")
        print(f"Balance:  ${balance:.2f}")
        print(f"Shares:   {shares}")
        print(f"RSI:      {last['rsi']:.2f}")
        print(f"MA Short: {last['ma_short']:.2f}  MA Long: {last['ma_long']:.2f}")
        if in_position:
            unrealized = (price - buy_price) * shares
            pct        = (price - buy_price) / buy_price * 100
            print(f"Held:     {bars_held} bars  |  Entry: ${buy_price:.2f}  |  Unrealized: ${unrealized:.2f} ({pct:+.2f}%)")

        # ===== BUY =====
        if not in_position and last["rsi"] < RSI_BUY:
            if bar_time.hour < NO_BUY_AFTER:
                shares      = int(balance // price)
                buy_price   = price
                balance    -= shares * price
                in_position = True
                bars_held   = 0

                order = MarketOrderRequest(
                    symbol=SYMBOL,
                    qty=shares,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                trading_client.submit_order(order)
                trades.append({"action": "BUY", "price": price, "shares": shares, "time": bar_time})
                print(f">>> BUY {shares} shares @ ${price:.2f}")
            else:
                print(">>> SKIPPED BUY - after 3pm ET")

        # ===== SELL =====
        elif in_position and bars_held >= MIN_BARS_HOLD:
            take_profit = price >= buy_price * (1 + PROFIT_TARGET)
            stop_loss   = price <= buy_price * (1 - STOP_LOSS)
            force_close = bar_time.hour == FORCE_CLOSE_H and bar_time.minute >= FORCE_CLOSE_M

            if take_profit or stop_loss or force_close:
                balance += shares * price
                pnl      = (price - buy_price) * shares

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
                trades.append({"action": "SELL", "price": price, "shares": shares, "time": bar_time, "pnl": pnl, "reason": reason})
                print(f">>> SELL {shares} shares @ ${price:.2f} | {reason} | PnL: ${pnl:.2f}")
                shares      = 0
                in_position = False
                bars_held   = 0

        time.sleep(60)

    except KeyboardInterrupt:
        wins   = [t for t in trades if t["action"] == "SELL" and t["pnl"] > 0]
        losses = [t for t in trades if t["action"] == "SELL" and t["pnl"] <= 0]
        print("\n========== SESSION SUMMARY ==========")
        print(f"Start Balance:  ${START_BALANCE:.2f}")
        print(f"Final Balance:  ${balance:.2f}")
        print(f"Net PnL:        ${balance - START_BALANCE:+.2f}")
        print(f"Total Trades:   {len(wins) + len(losses)}")
        print(f"Wins:           {len(wins)}   Losses: {len(losses)}")
        print("\n--- Trade Log ---")
        for t in trades:
            if t["action"] == "BUY":
                print(f"  BUY  {t['shares']} shares @ ${t['price']:.2f}  [{t['time']}]")
            else:
                print(f"  SELL {t['shares']} shares @ ${t['price']:.2f}  {t['reason']}  PnL: ${t['pnl']:.2f}  [{t['time']}]")
        break
