# AAPL Trade Bot

A paper trading bot for AAPL built with the Alpaca API. Uses RSI oversold signals to enter positions and exits on take profit, stop loss, or end-of-day force close. Sends real-time alerts to a Discord channel.

---

## Strategy

- **Entry:** RSI drops below 30 (oversold), only before 3:00 PM ET
- **Exit — Take Profit:** Price rises 0.8% above buy price
- **Exit — Stop Loss:** Price drops 0.5% below buy price
- **Exit — Force Close:** Any open position closed at 3:45 PM ET regardless
- **Minimum hold:** 20 bars must pass before any exit is evaluated

---

## Version History

### v2.0 — `stockbot_v2.0.py` *(latest)*
Full structural rewrite with more reliable alerting and daily lifecycle management.

**New features:**
- Market open/close alerts (`🟢 MARKET OPEN`, `🔴 MARKET CLOSED`) sent once per day
- Automatic daily summary at 4:01 PM ET — shows balance, net PnL, and win/loss count
- Daily flags (`market_open_sent`, `market_close_sent`, `daily_summary_sent`) reset each morning before 9 AM
- Heartbeat now fires every 15 minutes on the clock (e.g. :00, :15, :30, :45) instead of every 15 bars held — more consistent
- Startup Discord ping (`🚀 TRADING BOT STARTED`)
- Manual stop sends `🛑 BOT STOPPED MANUALLY` to Discord
- Data errors during retry loop now also alert Discord
- Stale data also pings Discord, not just console
- Stop loss tightened from 0.7% → 0.5%

---

### v1.01 — `stockbot_v1.01.py`

**Added over v1.0:**
- Improved console output (MA short/long added, unrealized P&L display)
- Stop loss tightened from 0.7% to 0.5%

---

### v1.0 — `stockbot_v1.0.py`
First working version. Console-only.

**Features:**
- RSI-based buy signal (RSI < 30)
- 5-bar and 20-bar moving averages calculated alongside RSI
- Take profit, stop loss, force close logic
- Stale data detection (skips bars older than 5 minutes)
- Safe fetch with automatic retry on connection errors
- Unrealized P&L shown in console while in a position
- Full session summary printed on Ctrl+C

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/aapl-trading-bot.git
cd aapl-trading-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
DISCORD_WEBHOOK=your_webhook_url_here
```

- Alpaca keys: [alpaca.markets](https://alpaca.markets)
- Discord webhook: Server Settings → Integrations → Webhooks

### 4. Run

```bash
python stockbot_v2.0.py
```

The bot idles outside market hours and begins trading automatically at 9:30 AM ET.

---

## Configuration

All tunable parameters are at the top of each script:

| Variable | v1.0 | v1.01 | v2.0 | Description |
|---|---|---|---|---|
| `SYMBOL` | AAPL | AAPL | AAPL | Stock to trade |
| `START_BALANCE` | 100,000 | 100,000 | 100,000 | Simulated starting cash |
| `PROFIT_TARGET` | 0.8% | 0.8% | 0.8% | Take profit threshold |
| `STOP_LOSS` | 0.7% | 0.5% | 0.5% | Stop loss threshold |
| `RSI_BUY` | 30 | 30 | 30 | RSI level to trigger buy |
| `MIN_BARS_HOLD` | 20 | 20 | 20 | Bars to hold before exit check |
| `NO_BUY_AFTER` | 3 PM | 3 PM | 3 PM | No new entries after this hour |
| `FORCE_CLOSE` | 3:45 PM | 3:45 PM | 3:45 PM | Hard close time |

---

## Notes

- All versions run in **paper trading** mode (`paper=True`) — no real money
- RSI uses a simple rolling average, not Wilder's smoothed EMA method
- `balance` is tracked locally for display; actual order execution goes through Alpaca

---

## Disclaimer

Personal project built for learning purposes. Not financial advice. Paper trading results do not guarantee live performance.
