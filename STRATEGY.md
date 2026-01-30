# Donchian Breakout Trading Strategy

A fully automated trend-following trading bot for Binance Futures that trades BTCUSDT, ETHUSDT, and SOLUSDT using Donchian channel breakouts with EMA trend filters.

## Table of Contents

- [Strategy Overview](#strategy-overview)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Configuration](#configuration)
- [Telegram Notifications](#telegram-notifications)
- [Running the Bot](#running-the-bot)
- [Strategy Parameters](#strategy-parameters)
- [Risk Management](#risk-management)
- [File Structure](#file-structure)
- [Troubleshooting](#troubleshooting)

---

## Strategy Overview

This is a **trend-following breakout strategy** that:

1. Identifies strong trends using EMA crossovers
2. Waits for high volatility conditions
3. Enters on Donchian channel breakouts
4. Adds to winning positions (pyramiding)
5. Exits using a trailing stop

**Key Characteristics:**
- Timeframe: 4-hour candles
- Check frequency: Every 30 minutes
- Markets: BTC, ETH, SOL (USDT perpetual futures)
- Risk per trade: 1% of account
- Maximum leverage: 3x
- Maximum positions per asset: 5 (1 initial + 4 pyramids)

---

## How It Works

### Step 1: Indicator Calculation (Every 30 minutes)

For each symbol (BTCUSDT, ETHUSDT, SOLUSDT), the bot:

1. Pulls the last 500 completed 4-hour candles
2. Calculates these indicators on the **previous completed candle** (not the current forming one):

| Indicator | Description |
|-----------|-------------|
| **EMA 55** | 55-period Exponential Moving Average |
| **EMA 200** | 200-period Exponential Moving Average |
| **ATR(14)** | 14-period Average True Range (volatility) |
| **Donchian High** | Highest high of last 55 candles |
| **Donchian Low** | Lowest low of last 55 candles |

### Step 2: Filter Checks

**ALL THREE filters must pass** before any entry is considered:

```
┌─────────────────────────────────────────────────────────────┐
│  VOLATILITY FILTER                                          │
│  ATR(14) ≥ Close × 2.8%                                     │
│  (Market must be volatile enough to trade)                  │
├─────────────────────────────────────────────────────────────┤
│  LONG TREND FILTER                                          │
│  Close > EMA55 > EMA200                                     │
│  (Price above both EMAs, fast EMA above slow)               │
├─────────────────────────────────────────────────────────────┤
│  SHORT TREND FILTER                                         │
│  Close < EMA55 < EMA200                                     │
│  (Price below both EMAs, fast EMA below slow)               │
└─────────────────────────────────────────────────────────────┘
```

### Step 3: Entry Signals

If filters pass and **no existing position**:

| Signal | Condition |
|--------|-----------|
| **LONG** | Current price crosses **above** 55-period Donchian High |
| **SHORT** | Current price crosses **below** 55-period Donchian Low |

### Step 4: Position Sizing

When entering a position:

```
1. Current Balance = X USDT
2. Risk Amount = X × 1% (risk 1% of account)
3. Stop Distance = ATR(14) × 2
4. Ideal Quantity = Risk Amount ÷ Stop Distance
5. Max Notional = Balance × 3 (3x leverage limit)
6. Final Quantity = MIN(Ideal Quantity, Max Notional ÷ Price)
7. Round to exchange precision (BTC: 0.001, ETH: 0.01, SOL: 0.1)
```

**Example:**
```
Balance: $1,000
Risk: $10 (1%)
ATR: $500
Stop Distance: $1,000 (ATR × 2)
Ideal Qty: 0.01 BTC ($10 ÷ $1,000)
BTC Price: $50,000
Max Qty: 0.06 BTC ($3,000 ÷ $50,000)
Final Qty: 0.01 BTC (smaller of ideal vs max)
```

### Step 5: Pyramiding (Adding to Winners)

When price moves **+1.5 × ATR** in your favor from the last entry:

1. Calculate new position size using current balance
2. Add to the position
3. Maximum 4 additions (5 total entries)

```
Initial Entry: $50,000
ATR at Entry: $500
Pyramid Threshold: $50,750 (+$750 = 1.5 × $500)

If price reaches $50,750 → Add second position
Next threshold: $51,500 → Add third position
...and so on up to 5 total
```

### Step 6: Trailing Stop Exit

Checked every loop iteration:

| Position | Trailing Stop |
|----------|---------------|
| **LONG** | Lowest low of last 10 completed 4H candles |
| **SHORT** | Highest high of last 10 completed 4H candles |

When price touches or crosses the trailing stop → **Close ENTIRE position** (all pyramids at once).

**No partial exits. No take-profit levels.**

### Step 7: Safety Rules

| Rule | Description |
|------|-------------|
| Max Leverage | Never exceed 3x (even if calculation allows more) |
| SOL Minimum | Don't trade SOLUSDT if balance < $400 |
| Trading Pause | If balance drops below $20, pause all new entries |

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Binance Futures account with API access
- API key with Futures trading permissions

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd p

# Install dependencies
pip install -r requirements.txt

# Set up credentials (copy and edit .env file)
cp .env.example .env

# Edit .env with your API keys:
# BINANCE_API_KEY=your_api_key
# BINANCE_API_SECRET=your_api_secret
# TELEGRAM_BOT_TOKEN=your_telegram_bot_token  (optional)
# TELEGRAM_CHAT_ID=your_telegram_chat_id      (optional)

# Run the bot
python main.py
```

---

## Configuration

### Default Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbols` | BTC, ETH, SOL | Trading pairs |
| `check_interval_seconds` | 1800 | Loop interval (30 min) |
| `risk_per_trade` | 0.01 | 1% risk per trade |
| `max_leverage` | 3 | Maximum leverage |
| `volatility_threshold` | 0.028 | Minimum ATR/price (2.8%) |
| `atr_stop_multiplier` | 2.0 | Stop = ATR × 2 |
| `pyramid_atr_multiplier` | 1.5 | Pyramid on +1.5 ATR |
| `max_pyramid_additions` | 4 | Max 4 adds (5 total) |
| `trailing_stop_period` | 10 | 10-candle trailing stop |
| `min_balance_for_sol` | 400 | Min balance for SOL |
| `min_balance_for_trading` | 20 | Min balance overall |

### Customizing Configuration

Edit `donchian_breakout_strategy.py` or pass arguments to `main.py`:

```python
from donchian_breakout_strategy import StrategyConfig

config = StrategyConfig(
    symbols=["BTCUSDT", "ETHUSDT"],  # Trade only BTC and ETH
    risk_per_trade=0.02,              # 2% risk instead of 1%
    max_leverage=2,                   # Lower leverage
    check_interval_seconds=3600       # Check every hour
)
```

---

## Telegram Notifications

The bot can send real-time notifications to Telegram for all important events.

### Setup

1. **Create a Telegram Bot:**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow the prompts
   - Save the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

2. **Get Your Chat ID:**
   - Search for `@userinfobot` on Telegram
   - Send any message to get your chat ID (a number like `123456789`)

3. **Configure the Bot:**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   ```

### Notification Events

| Event | Description |
|-------|-------------|
| **Startup** | Bot started, shows balance and symbols |
| **Shutdown** | Bot stopped |
| **Signal Detected** | Entry signal found (before execution) |
| **Position Opened** | New position entered with details |
| **Position Closed** | Position exited with P&L |
| **Pyramid Added** | Added to winning position |
| **Warning** | Balance too low, trading paused |
| **Error** | Unexpected error occurred |

### Example Notifications

**Startup:**
```
🚀 Trading Bot Started

🔴 LIVE
Symbols: BTCUSDT, ETHUSDT, SOLUSDT
Balance: $1,000.00 USDT
Time: 2025-01-15 10:30:00 UTC

Bot is now monitoring markets...
```

**Position Opened:**
```
🟢 New Position Opened

Symbol: BTCUSDT
Direction: 📈 LONG
Quantity: 0.0100
Entry Price: $50,000.00
Notional: $500.00
Risk: $10.00
Stop Distance: $1,000.00

Time: 2025-01-15 14:00:00 UTC
```

**Position Closed:**
```
🏁 Position Closed

Symbol: BTCUSDT
Side: LONG
Quantity: 0.0100
Entry: $50,000.00
Exit: $52,500.00
PnL: +$25.00 💚 (+5.00%)
Reason: Trailing stop hit at $51,800.00

💰 Time: 2025-01-15 18:30:00 UTC
```

### Command Line Options

```bash
# Disable notifications
python main.py --no-telegram

# Send notifications silently (no sound)
python main.py --telegram-silent

# Test Telegram connection
python main.py --test-telegram

# Pass credentials via command line
python main.py --telegram-token "token" --telegram-chat-id "id"
```

---

## Running the Bot

### Basic Usage

```bash
# 1. Make sure .env file is configured with your API keys
# 2. Run the bot
python main.py
```

### Command Line Options

```bash
# Show help
python main.py --help

# Use testnet (recommended for testing)
python main.py --testnet

# Run once and exit (for testing)
python main.py --once

# Custom symbols
python main.py --symbols BTCUSDT ETHUSDT

# Custom check interval (in seconds)
python main.py --interval 3600  # Check every hour

# Custom risk percentage
python main.py --risk 0.02  # 2% risk

# Custom leverage
python main.py --leverage 2  # 2x max leverage

# Pass credentials via arguments
python main.py --api-key "key" --api-secret "secret"
```

### Running 24/7

**Using screen (Linux/Mac):**
```bash
screen -S trading-bot
python main.py
# Press Ctrl+A, then D to detach
# Reconnect with: screen -r trading-bot
```

**Using tmux:**
```bash
tmux new -s trading-bot
python main.py
# Press Ctrl+B, then D to detach
# Reconnect with: tmux attach -t trading-bot
```

**Using systemd (Linux):**
```ini
# /etc/systemd/system/trading-bot.service
[Unit]
Description=Donchian Breakout Trading Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/p
# API keys are loaded from .env file automatically
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

### Testnet Setup

1. Go to https://testnet.binancefuture.com/
2. Create an account and get testnet API keys
3. Run with `--testnet` flag:

```bash
python main.py --testnet --api-key "testnet_key" --api-secret "testnet_secret"
```

---

## Strategy Parameters

### Indicator Settings

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| EMA Fast | 55 | Medium-term trend |
| EMA Slow | 200 | Long-term trend |
| ATR Period | 14 | Standard volatility measure |
| Donchian Period | 55 | Matches EMA fast for breakouts |
| Trailing Stop Period | 10 | ~40 hours of price action |

### Risk Settings

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Risk Per Trade | 1% | Conservative risk management |
| Stop Distance | 2 × ATR | Wide enough to avoid noise |
| Max Leverage | 3x | Limited for safety |
| Volatility Filter | 2.8% | Only trade volatile markets |

### Pyramiding Settings

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Pyramid Trigger | 1.5 × ATR | Add when clearly winning |
| Max Pyramids | 4 | Up to 5 total positions |

---

## Risk Management

### Position Risk

- Each trade risks exactly **1% of account balance**
- Stop distance is **2 × ATR** (adapts to volatility)
- Position size calculated to lose exactly 1% if stopped out

### Leverage Risk

- Maximum **3x leverage** hard-coded
- Uses **isolated margin** (losses limited to position margin)
- Each symbol managed independently

### Account Protection

- **$20 minimum**: Bot pauses all trading below this balance
- **$400 minimum for SOL**: Higher volatility asset requires more capital
- **State persistence**: Bot remembers positions across restarts

### Worst Case Scenarios

| Scenario | Protection |
|----------|------------|
| Flash crash | 2 × ATR stop provides buffer |
| Gap through stop | Isolated margin limits loss to position |
| Exchange issues | State file preserves position tracking |
| Bot crash | Positions remain, bot resumes on restart |

---

## File Structure

```
p/
├── main.py                       # Main entry point
├── donchian_breakout_strategy.py # Core strategy logic
├── telegram_notifier.py          # Telegram notification system
├── binance_futures.py            # Binance API client
├── requirements.txt              # Python dependencies
├── .env.example                  # Credential template
├── .env                          # Your API keys (create from .env.example)
├── .gitignore                    # Git ignore rules
├── README.md                     # API client documentation
├── STRATEGY.md                   # This file
│
# Generated at runtime:
├── trading_bot.log               # Activity log
└── strategy_state.json           # Position state persistence
```

### Key Files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point, loads .env, starts strategy |
| `donchian_breakout_strategy.py` | All strategy logic, indicators, position management |
| `telegram_notifier.py` | Telegram notifications for all trading events |
| `requirements.txt` | Python package dependencies |
| `.env` | Your API keys (not committed to git) |
| `strategy_state.json` | Tracks pyramid counts and entry prices |
| `trading_bot.log` | Full activity log for debugging |

---

## Troubleshooting

### Common Issues

**"API credentials required"**
```bash
# Set environment variables
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
```

**"Balance below minimum"**
- Deposit more funds or lower `min_balance_for_trading` in config

**"Not enough klines"**
- New trading pair, wait for more candle data
- Check if symbol exists on Binance Futures

**"Error -4046: No need to change margin type"**
- Normal message, margin type already set correctly

**"Error -2019: Insufficient margin"**
- Balance too low for position size
- Lower risk percentage or add funds

**"Error -1111: Precision is over max"**
- Quantity not rounded correctly (should be handled automatically)

### Logs

Check `trading_bot.log` for detailed activity:

```bash
# View last 100 lines
tail -100 trading_bot.log

# Follow live
tail -f trading_bot.log

# Search for errors
grep ERROR trading_bot.log
```

### State Reset

If state gets corrupted:

```bash
# Remove state file (bot will rebuild from exchange positions)
rm strategy_state.json
```

### Testing

```bash
# Run once to test without looping
python main.py --once --testnet

# Check current positions
python -c "
from binance_futures import BinanceFuturesClient
import os
client = BinanceFuturesClient(
    os.environ['BINANCE_API_KEY'],
    os.environ['BINANCE_API_SECRET']
)
print(client.get_open_positions())
"
```

---

## Disclaimer

This trading bot is provided for educational purposes only. Trading cryptocurrency futures involves substantial risk of loss. Past performance does not guarantee future results. Only trade with funds you can afford to lose. The authors are not responsible for any financial losses incurred from using this software.
