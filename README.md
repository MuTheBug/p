# Binance Futures Trading Client

A comprehensive Python client for Binance USDT-M Futures trading API with support for all order types including the new Algo Order API (TWAP, VP, and conditional orders).

## Features

- **Standard Orders**: Market, Limit, Post-Only
- **Conditional Orders** (Algo API): Stop Loss, Take Profit, Trailing Stop
- **Algorithmic Orders**: TWAP (Time-Weighted Average Price), VP (Volume Participation)
- **Position Management**: Leverage, Margin Type, Hedge Mode
- **Account Operations**: Balance, Positions, Income History
- **Market Data**: Prices, Order Book, Klines, Funding Rates

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd p

# Install dependencies
pip install requests
```

## Quick Start

```python
from binance_futures import BinanceFuturesClient, OrderSide, MarginType

# Initialize client
client = BinanceFuturesClient(
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=True  # Use testnet for testing
)

# Set up position
client.set_leverage("BTCUSDT", 10)
client.set_margin_type("BTCUSDT", MarginType.ISOLATED)

# Place a market order
order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)
print(f"Order ID: {order.order_id}, Status: {order.status}")
```

## Important: Algo API Migration (December 2025)

Since **December 9, 2025**, Binance migrated conditional orders to the Algo Service API. The following order types must now use the `algo_*` methods:

- `STOP_MARKET` → `algo_stop_market_order()`
- `STOP` (limit) → `algo_stop_limit_order()`
- `TAKE_PROFIT_MARKET` → `algo_take_profit_market_order()`
- `TAKE_PROFIT` (limit) → `algo_take_profit_limit_order()`
- `TRAILING_STOP_MARKET` → `algo_trailing_stop_order()`

Using the old endpoints will return error `-4120`.

## Order Types

### Standard Orders

```python
# Market Order
order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)

# Limit Order
order = client.limit_order("BTCUSDT", OrderSide.BUY, quantity=0.01, price=40000)

# Post-Only Order (maker only)
order = client.post_only_order("BTCUSDT", OrderSide.BUY, quantity=0.01, price=40000)

# Close Position
order = client.close_position_order("BTCUSDT", OrderSide.SELL)
```

### Conditional Orders (Algo API)

```python
from binance_futures import AlgoOrderType, WorkingType

# Stop Market Order
order = client.algo_stop_market_order(
    "BTCUSDT", OrderSide.SELL,
    quantity=0.01,
    stop_price=39000,
    working_type=WorkingType.MARK_PRICE
)

# Stop Limit Order
order = client.algo_stop_limit_order(
    "BTCUSDT", OrderSide.SELL,
    quantity=0.01,
    price=38900,
    stop_price=39000
)

# Take Profit Market Order
order = client.algo_take_profit_market_order(
    "BTCUSDT", OrderSide.SELL,
    quantity=0.01,
    stop_price=45000
)

# Take Profit Limit Order
order = client.algo_take_profit_limit_order(
    "BTCUSDT", OrderSide.SELL,
    quantity=0.01,
    price=45100,
    stop_price=45000
)

# Trailing Stop Order
order = client.algo_trailing_stop_order(
    "BTCUSDT", OrderSide.SELL,
    quantity=0.01,
    callback_rate=1.0,  # 1% callback
    activation_price=44000  # Optional
)

# Close Position with Stop Loss
order = client.algo_close_position_stop_loss(
    "BTCUSDT", OrderSide.SELL,
    stop_price=39000
)

# Close Position with Take Profit
order = client.algo_close_position_take_profit(
    "BTCUSDT", OrderSide.SELL,
    stop_price=45000
)
```

### TWAP Orders (Time-Weighted Average Price)

Execute large orders over a specified duration to minimize market impact.

```python
# Execute 1 BTC over 1 hour
order = client.place_twap_order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=1.0,
    duration=3600,  # seconds (5 min to 24 hours)
    limit_price=42000  # Optional limit price
)

print(f"TWAP Order ID: {order.client_algo_id}")
print(f"Success: {order.success}")
```

**TWAP Constraints:**
- Notional value: 10,000 - 1,000,000 USDT
- Duration: 300 - 86,400 seconds (5 min - 24 hours)
- Max 10 simultaneous orders per account

### VP Orders (Volume Participation)

Execute orders at a pace matching market volume.

```python
from binance_futures import VPUrgency

# Execute with low market impact
order = client.place_vp_order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=1.0,
    urgency=VPUrgency.LOW,  # LOW, MEDIUM, HIGH
    limit_price=42000  # Optional
)
```

**Urgency Levels:**
- `LOW`: Lower participation rate, minimal market impact
- `MEDIUM`: Balanced participation rate
- `HIGH`: Higher participation rate, faster execution

### Bracket Orders

Place entry order with stop loss and take profit in one call.

```python
# Market entry with SL and TP
orders = client.place_bracket_order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=0.01,
    entry_price=None,  # None for market entry
    stop_loss_price=39000,
    take_profit_price=45000
)

# Limit entry with SL and TP
orders = client.place_bracket_order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=0.01,
    entry_price=40000,
    stop_loss_price=39000,
    take_profit_price=45000
)
```

### Batch Orders

Place up to 5 orders in a single request.

```python
orders = [
    {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT",
     "quantity": 0.01, "price": 40000, "timeInForce": "GTC"},
    {"symbol": "BTCUSDT", "side": "SELL", "type": "LIMIT",
     "quantity": 0.01, "price": 45000, "timeInForce": "GTC"}
]
results = client.place_batch_orders(orders)
```

## Order Management

### Standard Orders

```python
# Query order
order = client.get_order("BTCUSDT", order_id=123456)

# Cancel order
order = client.cancel_order("BTCUSDT", order_id=123456)

# Cancel all orders for symbol
client.cancel_all_orders("BTCUSDT")

# Get open orders
open_orders = client.get_open_orders("BTCUSDT")

# Get all orders (history)
all_orders = client.get_all_orders("BTCUSDT", limit=100)
```

### Algo Orders

```python
# Query algo order
order = client.get_algo_order("BTCUSDT", algo_id=123456)

# Cancel algo order
order = client.cancel_algo_order("BTCUSDT", algo_id=123456)

# Cancel all algo orders
client.cancel_all_algo_orders("BTCUSDT")

# Get open algo orders
open_algos = client.get_open_algo_orders("BTCUSDT")

# Get all algo orders (history)
all_algos = client.get_all_algo_orders("BTCUSDT", limit=100)
```

### TWAP/VP Orders

```python
# Get open TWAP/VP orders
open_orders = client.get_twap_vp_open_orders()

# Get historical orders
history = client.get_twap_vp_historical_orders(
    symbol="BTCUSDT",
    start_time=1700000000000,
    end_time=1700100000000
)

# Get sub-orders (child orders)
sub_orders = client.get_twap_vp_sub_orders(algo_id=123456)

# Cancel TWAP/VP order
client.cancel_twap_vp_order(algo_id=123456)
```

## Position Management

```python
# Set leverage (1-125x depending on symbol)
client.set_leverage("BTCUSDT", 20)

# Set margin type
client.set_margin_type("BTCUSDT", MarginType.ISOLATED)  # or CROSSED

# Set position mode
client.set_position_mode(hedge_mode=True)  # True for hedge, False for one-way

# Get position mode
mode = client.get_position_mode()

# Get positions
positions = client.get_positions("BTCUSDT")

# Get only open positions (non-zero)
open_positions = client.get_open_positions()

# Adjust isolated margin
client.adjust_position_margin(
    "BTCUSDT",
    amount=100,
    add_margin=True  # True to add, False to remove
)
```

## Account Information

```python
# Get full account info
account = client.get_account()
print(f"Total Balance: {account['totalWalletBalance']}")
print(f"Available: {account['availableBalance']}")

# Get all asset balances
balances = client.get_balance()

# Get specific asset balance
usdt = client.get_asset_balance("USDT")
print(f"USDT Balance: {usdt['balance']}")

# Get income history (PnL, funding, commissions)
from binance_futures import IncomeType

income = client.get_income_history(
    symbol="BTCUSDT",
    income_type=IncomeType.REALIZED_PNL,
    limit=100
)

# Get leverage brackets
brackets = client.get_leverage_brackets("BTCUSDT")
```

## Market Data

```python
# Get current price
price = client.get_ticker_price("BTCUSDT")

# Get 24hr statistics
stats = client.get_ticker_24hr("BTCUSDT")

# Get order book
depth = client.get_order_book("BTCUSDT", limit=100)

# Get klines/candlesticks
klines = client.get_klines(
    "BTCUSDT",
    interval="1h",
    limit=100
)

# Get mark price and funding rate
mark = client.get_mark_price("BTCUSDT")

# Get funding rate history
funding = client.get_funding_rate_history("BTCUSDT", limit=100)

# Get exchange info (trading rules)
info = client.get_exchange_info()

# Get symbol-specific info
symbol_info = client.get_symbol_info("BTCUSDT")
```

## Utility Methods

```python
# Get price and quantity precision
precision = client.get_precision("BTCUSDT")
print(f"Price precision: {precision['price_precision']}")
print(f"Quantity precision: {precision['quantity_precision']}")

# Round price to correct precision
price = client.round_price("BTCUSDT", 42000.123456789)

# Round quantity to correct precision
qty = client.round_quantity("BTCUSDT", 0.123456789)

# Calculate position size based on risk
position_size = client.calculate_position_size(
    symbol="BTCUSDT",
    risk_amount=100,  # Risk $100
    entry_price=42000,
    stop_loss_price=41000
)
```

## WebSocket User Data Stream

```python
# Create listen key
listen_key = client.create_listen_key()

# Keep alive (call every 30 minutes)
client.keepalive_listen_key()

# Close stream
client.close_listen_key()
```

## Enums Reference

```python
from binance_futures import (
    OrderSide,      # BUY, SELL
    OrderType,      # LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, etc.
    AlgoOrderType,  # STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
    TimeInForce,    # GTC, IOC, FOK, GTX
    PositionSide,   # BOTH, LONG, SHORT
    MarginType,     # ISOLATED, CROSSED
    WorkingType,    # MARK_PRICE, CONTRACT_PRICE
    VPUrgency,      # LOW, MEDIUM, HIGH
    IncomeType,     # REALIZED_PNL, FUNDING_FEE, COMMISSION, etc.
)
```

## Error Handling

```python
from binance_futures import BinanceFuturesError

try:
    order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)
except BinanceFuturesError as e:
    print(f"Error Code: {e.code}")
    print(f"Error Message: {e.message}")

    # Common error codes:
    # -4120: Use Algo API for conditional orders
    # -2019: Margin is insufficient
    # -1111: Precision is over the maximum
    # -1121: Invalid symbol
```

## Testnet

Always test with the testnet before using real funds:

```python
client = BinanceFuturesClient(
    api_key="testnet_api_key",
    api_secret="testnet_api_secret",
    testnet=True
)
```

Testnet URL: https://testnet.binancefuture.com

## API Rate Limits

- Orders: 1200 requests per minute
- Order updates: 10 orders per second per symbol
- TWAP/VP: Max 10 simultaneous orders

## License

MIT License

---

## Trendline Strategy Trading Bot

This project includes a complete trading bot implementing the **Trendline Strategy** - a swing trading method using trendlines, clear rules, and strict risk control.

### Strategy Overview

The strategy is based on two key concepts:
- **Action Line**: Where to enter a trade
- **Safety Line**: Where to exit if the trade doesn't work out

**Three setup types are supported:**

1. **Trendline Bounce**: Enter when price touches and respects an existing trendline
2. **Trendline Break (2-point)**: Enter when price breaks a 2-touchpoint trendline
3. **Trendline Break (3-point)**: Enter when price breaks a 3+ touchpoint trendline (more reliable)

### Quick Start

```bash
# 1. Copy the example environment file
cp .env.example .env

# 2. Edit .env with your API keys
nano .env

# 3. Install dependencies
pip install requests numpy python-dotenv

# 4. Run in signal-only mode (recommended for testing)
python run_bot.py --symbols BTCUSDT ETHUSDT

# 5. Run with auto-trading (use testnet first!)
python run_bot.py --auto-trade --testnet
```

### Configuration

Create a `.env` file with the following variables (see `.env.example`):

```bash
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# Telegram (for notifications)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=true

# Trading
TRADING_SYMBOLS=BTCUSDT,ETHUSDT
TIMEFRAME=4h
RISK_PER_TRADE_PCT=1.0
LEVERAGE=10
AUTO_TRADE=false
```

### Usage Examples

#### Python API

```python
from binance_futures import BinanceFuturesClient
from telegram_notifier import TelegramNotifier
from trendline_strategy import TrendlineStrategyBot

# Initialize clients
client = BinanceFuturesClient(api_key, api_secret, testnet=True)
notifier = TelegramNotifier(bot_token, chat_id)

# Create bot with custom config
bot = TrendlineStrategyBot(
    binance_client=client,
    telegram_notifier=notifier,
    config={
        "timeframe": "4h",
        "risk_per_trade_pct": 1.0,
        "leverage": 10,
        "enable_trailing_stop": True,
        "take_profit_rr_ratio": 2.0,  # 2:1 risk-reward
    }
)

# Run in signal-only mode
bot.run(symbols=["BTCUSDT", "ETHUSDT"], auto_trade=False)

# Or scan for setups manually
setups = bot.scan_for_setups("BTCUSDT")
for setup in setups:
    print(f"Found: {setup.setup_type.value} {setup.direction}")
```

#### Command Line

```bash
# Dry run - scan for setups without trading
python run_bot.py --dry-run --symbols BTCUSDT

# Signal-only mode (default)
python run_bot.py --symbols BTCUSDT ETHUSDT SOLUSDT

# Enable auto-trading on testnet
python run_bot.py --auto-trade --testnet

# Verbose logging
python run_bot.py -v --symbols BTCUSDT
```

### Telegram Notifications

The bot sends notifications for:
- Trade entries with full details (entry, SL, TP, R:R ratio)
- Trade exits with PnL summary
- Stop loss/take profit hits
- Trailing stop updates
- Signal alerts for detected setups
- Errors and warnings

Example notification:
```
📈 TRADE ENTRY 🟢
━━━━━━━━━━━━━━━━━━━━
Symbol: BTCUSDT
Side: LONG
Quantity: 0.01
Entry Price: $42,000.00
Stop Loss: $41,000.00 (2.38%)
Take Profit: $44,000.00 (4.76%)
Risk/Reward: 1:2.00

Strategy: Trendline Strategy
Setup: Trendline Bounce

Details:
  • Touchpoints: 3
  • Confidence: 80%
  • Time Span: 200h
```

### Risk Management

The bot includes comprehensive risk management:
- **Position sizing** based on % risk per trade
- **Maximum positions** limit
- **Trailing stops** along trendlines
- **Safety line validation** before entry
- **Automatic stop loss** placement

### Files

| File | Description |
|------|-------------|
| `binance_futures.py` | Binance Futures API client |
| `telegram_notifier.py` | Telegram notification service |
| `trendline_strategy.py` | Trendline Strategy bot |
| `config.py` | Configuration management |
| `run_bot.py` | Bot runner script |
| `.env.example` | Example environment file |

## References

- [Binance Futures API Documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info)
- [New Algo Order API](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order)
- [TWAP Orders](https://developers.binance.com/docs/algo/future-algo/Time-Weighted-Average-Price-New-Order)
- [VP Orders](https://developers.binance.com/docs/algo/future-algo)
- [API Change Log](https://developers.binance.com/docs/derivatives/change-log)
- [Trendline Strategy by Tori Trades](https://www.tradezella.com/strategies/trendline-strategy)
