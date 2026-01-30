#!/usr/bin/env python3
"""
Donchian Breakout Trading Strategy

A trend-following strategy using EMA filters, ATR-based volatility filter,
and Donchian channel breakouts for entries. Features pyramiding and
trailing stop exits.

Strategy Logic:
1. Entry signals based on 55-period Donchian channel breakouts
2. Trend filters: EMA55 > EMA200 for longs, EMA55 < EMA200 for shorts
3. Volatility filter: ATR(14) >= 2.8% of close price
4. Position sizing based on 1% risk with 2*ATR stop distance
5. Pyramiding up to 4 additions (5 total positions)
6. Trailing stop based on 10-period lowest low / highest high
"""

import time
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from binance_futures import (
    BinanceFuturesClient,
    OrderSide,
    MarginType,
    PositionSide,
    BinanceFuturesError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)


# ==================== Configuration ====================

@dataclass
class StrategyConfig:
    """Strategy configuration parameters."""
    # Trading pairs
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    # Indicator periods
    ema_fast_period: int = 55
    ema_slow_period: int = 200
    atr_period: int = 14
    donchian_period: int = 55
    trailing_stop_period: int = 10

    # Risk parameters
    risk_per_trade: float = 0.01  # 1% risk per trade
    atr_stop_multiplier: float = 2.0  # Stop distance = ATR * 2
    volatility_threshold: float = 0.028  # Minimum ATR/close ratio (2.8%)

    # Pyramiding
    pyramid_atr_multiplier: float = 1.5  # Add position when price moves 1.5 * ATR in favor
    max_pyramid_additions: int = 4  # Max 4 additions (5 total positions)

    # Leverage and margin
    max_leverage: int = 3
    use_isolated_margin: bool = True

    # Safety rules
    min_balance_for_sol: float = 400.0  # Don't trade SOL below this balance
    min_balance_for_trading: float = 20.0  # Stop all trading below this balance

    # Loop settings
    check_interval_seconds: int = 1800  # 30 minutes
    kline_interval: str = "4h"
    kline_limit: int = 500

    # Quantity precision per symbol (min lot size)
    quantity_precision: Dict[str, int] = field(default_factory=lambda: {
        "BTCUSDT": 3,   # 0.001
        "ETHUSDT": 2,   # 0.01
        "SOLUSDT": 1    # 0.1
    })


@dataclass
class PositionState:
    """Tracks state for a position."""
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    pyramid_count: int = 0  # Number of additions (0 = initial position only)
    last_pyramid_price: float = 0.0  # Price at last pyramid addition
    atr_at_entry: float = 0.0  # ATR when position was opened

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PositionState":
        return cls(**data)


# ==================== Technical Indicators ====================

def calculate_ema(closes: List[float], period: int) -> float:
    """
    Calculate Exponential Moving Average.

    Args:
        closes: List of closing prices (oldest first)
        period: EMA period

    Returns:
        Current EMA value
    """
    if len(closes) < period:
        return closes[-1] if closes else 0.0

    multiplier = 2 / (period + 1)

    # Start with SMA for first 'period' values
    ema = sum(closes[:period]) / period

    # Calculate EMA for remaining values
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema

    return ema


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    """
    Calculate Average True Range.

    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ATR period

    Returns:
        Current ATR value
    """
    if len(closes) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    # Use Wilder's smoothing (RMA)
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr


def calculate_donchian(highs: List[float], lows: List[float], period: int) -> Tuple[float, float]:
    """
    Calculate Donchian Channel high and low.

    Args:
        highs: List of high prices
        lows: List of low prices
        period: Donchian period

    Returns:
        Tuple of (donchian_high, donchian_low)
    """
    if len(highs) < period:
        return max(highs) if highs else 0.0, min(lows) if lows else 0.0

    donchian_high = max(highs[-period:])
    donchian_low = min(lows[-period:])

    return donchian_high, donchian_low


def calculate_trailing_stop(highs: List[float], lows: List[float], period: int, is_long: bool) -> float:
    """
    Calculate trailing stop level.

    Args:
        highs: List of high prices
        lows: List of low prices
        period: Lookback period
        is_long: True for long position, False for short

    Returns:
        Trailing stop price
    """
    if is_long:
        # For long: lowest low of last N candles
        return min(lows[-period:]) if len(lows) >= period else min(lows)
    else:
        # For short: highest high of last N candles
        return max(highs[-period:]) if len(highs) >= period else max(highs)


# ==================== Signal Detection ====================

@dataclass
class MarketData:
    """Processed market data for a symbol."""
    symbol: str
    current_price: float
    prev_close: float
    ema_fast: float
    ema_slow: float
    atr: float
    donchian_high: float
    donchian_low: float
    trailing_stop_long: float
    trailing_stop_short: float

    # Raw data for trailing stop calculation
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)


def parse_klines(klines: List[List]) -> Tuple[List[float], List[float], List[float], List[float]]:
    """
    Parse kline data into OHLC lists.

    Args:
        klines: Raw kline data from Binance API

    Returns:
        Tuple of (opens, highs, lows, closes)
    """
    opens = []
    highs = []
    lows = []
    closes = []

    for kline in klines:
        opens.append(float(kline[1]))
        highs.append(float(kline[2]))
        lows.append(float(kline[3]))
        closes.append(float(kline[4]))

    return opens, highs, lows, closes


def calculate_indicators(
    client: BinanceFuturesClient,
    symbol: str,
    config: StrategyConfig
) -> Optional[MarketData]:
    """
    Calculate all indicators for a symbol.

    Args:
        client: Binance client
        symbol: Trading pair
        config: Strategy configuration

    Returns:
        MarketData object or None if error
    """
    try:
        # Get klines (candlesticks)
        klines = client.get_klines(
            symbol=symbol,
            interval=config.kline_interval,
            limit=config.kline_limit
        )

        if len(klines) < config.ema_slow_period + 1:
            logger.warning(f"{symbol}: Not enough klines for indicator calculation")
            return None

        opens, highs, lows, closes = parse_klines(klines)

        # Use completed candles (exclude current forming candle)
        completed_highs = highs[:-1]
        completed_lows = lows[:-1]
        completed_closes = closes[:-1]

        # Get current price
        ticker = client.get_ticker_price(symbol)
        current_price = float(ticker["price"])

        # Previous candle close
        prev_close = completed_closes[-1]

        # Calculate EMAs on completed candles
        ema_fast = calculate_ema(completed_closes, config.ema_fast_period)
        ema_slow = calculate_ema(completed_closes, config.ema_slow_period)

        # Calculate ATR on completed candles
        atr = calculate_atr(completed_highs, completed_lows, completed_closes, config.atr_period)

        # Calculate Donchian channels on completed candles
        donchian_high, donchian_low = calculate_donchian(
            completed_highs, completed_lows, config.donchian_period
        )

        # Calculate trailing stops using last N completed candles
        trailing_stop_long = calculate_trailing_stop(
            completed_highs, completed_lows, config.trailing_stop_period, is_long=True
        )
        trailing_stop_short = calculate_trailing_stop(
            completed_highs, completed_lows, config.trailing_stop_period, is_long=False
        )

        return MarketData(
            symbol=symbol,
            current_price=current_price,
            prev_close=prev_close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            atr=atr,
            donchian_high=donchian_high,
            donchian_low=donchian_low,
            trailing_stop_long=trailing_stop_long,
            trailing_stop_short=trailing_stop_short,
            highs=completed_highs,
            lows=completed_lows
        )

    except BinanceFuturesError as e:
        logger.error(f"{symbol}: Binance API error: {e.code} - {e.message}")
        return None
    except Exception as e:
        logger.error(f"{symbol}: Error calculating indicators: {e}")
        return None


def check_filters(data: MarketData, config: StrategyConfig) -> Tuple[bool, bool, str]:
    """
    Check if all filters pass for potential entry.

    Args:
        data: Market data with indicators
        config: Strategy configuration

    Returns:
        Tuple of (long_filters_pass, short_filters_pass, reason)
    """
    # Volatility filter: ATR(14) >= close * 2.8%
    volatility_ratio = data.atr / data.prev_close
    volatility_pass = volatility_ratio >= config.volatility_threshold

    if not volatility_pass:
        return False, False, f"Volatility too low: {volatility_ratio:.4f} < {config.volatility_threshold}"

    # Trend filter for long: close > EMA55 > EMA200
    long_trend = data.prev_close > data.ema_fast > data.ema_slow

    # Trend filter for short: close < EMA55 < EMA200
    short_trend = data.prev_close < data.ema_fast < data.ema_slow

    if not long_trend and not short_trend:
        return False, False, f"No trend alignment: close={data.prev_close:.2f}, EMA55={data.ema_fast:.2f}, EMA200={data.ema_slow:.2f}"

    return long_trend, short_trend, "Filters passed"


def check_entry_signal(data: MarketData, config: StrategyConfig) -> Tuple[Optional[str], str]:
    """
    Check for entry signals.

    Args:
        data: Market data with indicators
        config: Strategy configuration

    Returns:
        Tuple of (signal_type or None, reason)
    """
    # Check filters first
    long_filters_pass, short_filters_pass, filter_reason = check_filters(data, config)

    if not long_filters_pass and not short_filters_pass:
        return None, filter_reason

    # Long signal: current price crosses above Donchian High
    if long_filters_pass and data.current_price > data.donchian_high:
        return "LONG", f"Long breakout: price {data.current_price:.2f} > Donchian high {data.donchian_high:.2f}"

    # Short signal: current price crosses below Donchian Low
    if short_filters_pass and data.current_price < data.donchian_low:
        return "SHORT", f"Short breakout: price {data.current_price:.2f} < Donchian low {data.donchian_low:.2f}"

    return None, "No breakout signal"


# ==================== Position Management ====================

def get_usdt_balance(client: BinanceFuturesClient) -> float:
    """Get current USDT wallet balance."""
    try:
        balance = client.get_asset_balance("USDT")
        return float(balance.get("balance", 0))
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return 0.0


def get_available_balance(client: BinanceFuturesClient) -> float:
    """Get available USDT balance for trading."""
    try:
        balance = client.get_asset_balance("USDT")
        return float(balance.get("availableBalance", 0))
    except Exception as e:
        logger.error(f"Error getting available balance: {e}")
        return 0.0


def get_current_position(client: BinanceFuturesClient, symbol: str) -> Optional[Dict]:
    """
    Get current position for a symbol.

    Returns:
        Position dict or None if no position
    """
    try:
        positions = client.get_positions(symbol)
        for pos in positions:
            qty = float(pos.get("positionAmt", 0))
            if qty != 0:
                return pos
        return None
    except Exception as e:
        logger.error(f"{symbol}: Error getting position: {e}")
        return None


def calculate_position_size(
    balance: float,
    risk_amount: float,
    atr: float,
    atr_multiplier: float,
    current_price: float,
    max_leverage: int,
    symbol: str,
    config: StrategyConfig
) -> float:
    """
    Calculate position size based on risk parameters.

    Args:
        balance: Current USDT balance
        risk_amount: Amount to risk (balance * risk_per_trade)
        atr: Current ATR value
        atr_multiplier: Multiplier for stop distance
        current_price: Current market price
        max_leverage: Maximum allowed leverage
        symbol: Trading pair symbol
        config: Strategy configuration

    Returns:
        Final quantity to trade
    """
    # Stop distance = ATR * 2
    stop_distance = atr * atr_multiplier

    # Ideal quantity based on risk
    if stop_distance > 0:
        ideal_quantity = risk_amount / stop_distance
    else:
        ideal_quantity = 0

    # Max notional with leverage
    max_notional = balance * max_leverage
    max_quantity = max_notional / current_price

    # Take the smaller of ideal and max
    quantity = min(ideal_quantity, max_quantity)

    # Round to symbol precision
    precision = config.quantity_precision.get(symbol, 3)
    quantity = round(quantity, precision)

    return quantity


def setup_leverage_and_margin(
    client: BinanceFuturesClient,
    symbol: str,
    config: StrategyConfig
) -> bool:
    """
    Set up leverage and margin type for a symbol.

    Returns:
        True if successful
    """
    try:
        # Set leverage
        client.set_leverage(symbol, config.max_leverage)
        logger.info(f"{symbol}: Leverage set to {config.max_leverage}x")

        # Set margin type (isolated recommended)
        if config.use_isolated_margin:
            try:
                client.set_margin_type(symbol, MarginType.ISOLATED)
                logger.info(f"{symbol}: Margin type set to ISOLATED")
            except BinanceFuturesError as e:
                # Error -4046 means already set to that margin type
                if e.code != -4046:
                    raise

        return True

    except BinanceFuturesError as e:
        logger.error(f"{symbol}: Error setting leverage/margin: {e.code} - {e.message}")
        return False


# ==================== Order Execution ====================

def open_position(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: float,
    config: StrategyConfig
) -> Optional[Dict]:
    """
    Open a new position.

    Args:
        client: Binance client
        symbol: Trading pair
        side: "LONG" or "SHORT"
        quantity: Position size
        config: Strategy configuration

    Returns:
        Order result or None if failed
    """
    try:
        # Set up leverage and margin
        if not setup_leverage_and_margin(client, symbol, config):
            return None

        # Determine order side
        order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL

        # Place market order
        order = client.market_order(
            symbol=symbol,
            side=order_side,
            quantity=quantity
        )

        logger.info(
            f"{symbol}: Opened {side} position - Qty: {quantity}, "
            f"Avg Price: {order.avg_price}, Order ID: {order.order_id}"
        )

        return {
            "order_id": order.order_id,
            "avg_price": float(order.avg_price),
            "executed_qty": float(order.executed_qty),
            "side": side
        }

    except BinanceFuturesError as e:
        logger.error(f"{symbol}: Error opening position: {e.code} - {e.message}")
        return None


def close_position(
    client: BinanceFuturesClient,
    symbol: str,
    position: Dict,
    reason: str
) -> bool:
    """
    Close entire position.

    Args:
        client: Binance client
        symbol: Trading pair
        position: Current position dict from API
        reason: Reason for closing

    Returns:
        True if successful
    """
    try:
        qty = abs(float(position.get("positionAmt", 0)))
        if qty == 0:
            return True

        # Determine side to close
        is_long = float(position.get("positionAmt", 0)) > 0
        close_side = OrderSide.SELL if is_long else OrderSide.BUY

        # Place market order to close
        order = client.market_order(
            symbol=symbol,
            side=close_side,
            quantity=qty,
            reduce_only=True
        )

        entry_price = float(position.get("entryPrice", 0))
        exit_price = float(order.avg_price)
        pnl = float(position.get("unrealizedProfit", 0))

        logger.info(
            f"{symbol}: CLOSED {'LONG' if is_long else 'SHORT'} position - "
            f"Entry: {entry_price:.2f}, Exit: {exit_price:.2f}, PnL: {pnl:.2f} USDT - "
            f"Reason: {reason}"
        )

        return True

    except BinanceFuturesError as e:
        logger.error(f"{symbol}: Error closing position: {e.code} - {e.message}")
        return False


def add_to_position(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: float
) -> Optional[Dict]:
    """
    Add to existing position (pyramid).

    Args:
        client: Binance client
        symbol: Trading pair
        side: "LONG" or "SHORT"
        quantity: Amount to add

    Returns:
        Order result or None if failed
    """
    try:
        order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL

        order = client.market_order(
            symbol=symbol,
            side=order_side,
            quantity=quantity
        )

        logger.info(
            f"{symbol}: Added to {side} position - Qty: {quantity}, "
            f"Price: {order.avg_price}"
        )

        return {
            "order_id": order.order_id,
            "avg_price": float(order.avg_price),
            "executed_qty": float(order.executed_qty)
        }

    except BinanceFuturesError as e:
        logger.error(f"{symbol}: Error adding to position: {e.code} - {e.message}")
        return None


# ==================== State Management ====================

STATE_FILE = "strategy_state.json"


def save_state(positions: Dict[str, PositionState]) -> None:
    """Save position states to file."""
    try:
        data = {symbol: state.to_dict() for symbol, state in positions.items()}
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state: {e}")


def load_state() -> Dict[str, PositionState]:
    """Load position states from file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
            return {symbol: PositionState.from_dict(state) for symbol, state in data.items()}
    except Exception as e:
        logger.error(f"Error loading state: {e}")
    return {}


# ==================== Main Strategy Loop ====================

class DonchianBreakoutStrategy:
    """Main strategy class."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        config: Optional[StrategyConfig] = None,
        testnet: bool = False
    ):
        self.client = BinanceFuturesClient(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        self.config = config or StrategyConfig()
        self.position_states: Dict[str, PositionState] = load_state()
        self.running = False

        logger.info("Strategy initialized")
        logger.info(f"Symbols: {self.config.symbols}")
        logger.info(f"Risk per trade: {self.config.risk_per_trade * 100}%")
        logger.info(f"Max leverage: {self.config.max_leverage}x")
        logger.info(f"Testnet: {testnet}")

    def check_safety_rules(self, balance: float, symbol: str) -> Tuple[bool, str]:
        """
        Check safety rules before trading.

        Returns:
            Tuple of (can_trade, reason)
        """
        # Check minimum balance for any trading
        if balance < self.config.min_balance_for_trading:
            return False, f"Balance ${balance:.2f} below minimum ${self.config.min_balance_for_trading}"

        # Check minimum balance for SOL
        if symbol == "SOLUSDT" and balance < self.config.min_balance_for_sol:
            return False, f"Balance ${balance:.2f} below ${self.config.min_balance_for_sol} required for SOL"

        return True, "OK"

    def process_symbol(self, symbol: str, balance: float) -> None:
        """Process a single symbol."""
        logger.info(f"--- Processing {symbol} ---")

        # Check safety rules
        can_trade, reason = self.check_safety_rules(balance, symbol)
        if not can_trade:
            logger.info(f"{symbol}: Skipping - {reason}")
            return

        # Calculate indicators
        data = calculate_indicators(self.client, symbol, self.config)
        if data is None:
            return

        logger.info(
            f"{symbol}: Price={data.current_price:.2f}, EMA55={data.ema_fast:.2f}, "
            f"EMA200={data.ema_slow:.2f}, ATR={data.atr:.2f}, "
            f"Donchian=[{data.donchian_low:.2f}, {data.donchian_high:.2f}]"
        )

        # Get current position from exchange
        position = get_current_position(self.client, symbol)
        has_position = position is not None and float(position.get("positionAmt", 0)) != 0

        if has_position:
            self.manage_existing_position(symbol, position, data, balance)
        else:
            self.check_for_new_entry(symbol, data, balance)

    def manage_existing_position(
        self,
        symbol: str,
        position: Dict,
        data: MarketData,
        balance: float
    ) -> None:
        """Manage an existing position."""
        qty = float(position.get("positionAmt", 0))
        is_long = qty > 0
        entry_price = float(position.get("entryPrice", 0))
        unrealized_pnl = float(position.get("unrealizedProfit", 0))

        side = "LONG" if is_long else "SHORT"

        logger.info(
            f"{symbol}: Existing {side} position - "
            f"Qty: {abs(qty)}, Entry: {entry_price:.2f}, uPnL: {unrealized_pnl:.2f}"
        )

        # Step 5: Check trailing stop
        if is_long:
            trailing_stop = data.trailing_stop_long
            if data.current_price <= trailing_stop:
                close_position(
                    self.client, symbol, position,
                    f"Trailing stop hit at {trailing_stop:.2f}"
                )
                # Remove from state
                if symbol in self.position_states:
                    del self.position_states[symbol]
                    save_state(self.position_states)
                return
        else:
            trailing_stop = data.trailing_stop_short
            if data.current_price >= trailing_stop:
                close_position(
                    self.client, symbol, position,
                    f"Trailing stop hit at {trailing_stop:.2f}"
                )
                # Remove from state
                if symbol in self.position_states:
                    del self.position_states[symbol]
                    save_state(self.position_states)
                return

        logger.info(f"{symbol}: Trailing stop at {trailing_stop:.2f}")

        # Step 4: Check for pyramiding
        self.check_pyramid(symbol, position, data, balance, side)

    def check_pyramid(
        self,
        symbol: str,
        position: Dict,
        data: MarketData,
        balance: float,
        side: str
    ) -> None:
        """Check if we should add to the position (pyramid)."""
        # Get or create position state
        if symbol not in self.position_states:
            entry_price = float(position.get("entryPrice", 0))
            qty = abs(float(position.get("positionAmt", 0)))
            self.position_states[symbol] = PositionState(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=qty,
                pyramid_count=0,
                last_pyramid_price=entry_price,
                atr_at_entry=data.atr
            )
            save_state(self.position_states)

        state = self.position_states[symbol]

        # Check if max pyramids reached
        if state.pyramid_count >= self.config.max_pyramid_additions:
            logger.debug(f"{symbol}: Max pyramid count reached ({state.pyramid_count})")
            return

        # Calculate pyramid threshold
        atr_distance = state.atr_at_entry * self.config.pyramid_atr_multiplier

        if side == "LONG":
            # Price must move up by 1.5 * ATR from last pyramid price
            threshold = state.last_pyramid_price + atr_distance
            should_pyramid = data.current_price >= threshold
        else:
            # Price must move down by 1.5 * ATR from last pyramid price
            threshold = state.last_pyramid_price - atr_distance
            should_pyramid = data.current_price <= threshold

        if not should_pyramid:
            logger.debug(
                f"{symbol}: Pyramid threshold not reached. "
                f"Current: {data.current_price:.2f}, Threshold: {threshold:.2f}"
            )
            return

        # Calculate new position size
        risk_amount = balance * self.config.risk_per_trade
        new_quantity = calculate_position_size(
            balance=balance,
            risk_amount=risk_amount,
            atr=data.atr,
            atr_multiplier=self.config.atr_stop_multiplier,
            current_price=data.current_price,
            max_leverage=self.config.max_leverage,
            symbol=symbol,
            config=self.config
        )

        if new_quantity <= 0:
            logger.warning(f"{symbol}: Calculated pyramid quantity is 0")
            return

        # Add to position
        result = add_to_position(self.client, symbol, side, new_quantity)

        if result:
            # Update state
            state.pyramid_count += 1
            state.last_pyramid_price = data.current_price
            state.quantity += new_quantity
            save_state(self.position_states)

            logger.info(
                f"{symbol}: Pyramid #{state.pyramid_count} added. "
                f"Total positions: {state.pyramid_count + 1}"
            )

    def check_for_new_entry(self, symbol: str, data: MarketData, balance: float) -> None:
        """Check for new entry signal."""
        # Clear any stale state
        if symbol in self.position_states:
            del self.position_states[symbol]
            save_state(self.position_states)

        # Check for entry signal
        signal, reason = check_entry_signal(data, self.config)

        if signal is None:
            logger.info(f"{symbol}: No entry signal - {reason}")
            return

        logger.info(f"{symbol}: Entry signal detected - {reason}")

        # Calculate position size
        risk_amount = balance * self.config.risk_per_trade
        quantity = calculate_position_size(
            balance=balance,
            risk_amount=risk_amount,
            atr=data.atr,
            atr_multiplier=self.config.atr_stop_multiplier,
            current_price=data.current_price,
            max_leverage=self.config.max_leverage,
            symbol=symbol,
            config=self.config
        )

        if quantity <= 0:
            logger.warning(f"{symbol}: Calculated quantity is 0, skipping entry")
            return

        logger.info(
            f"{symbol}: Preparing {signal} entry - "
            f"Risk: ${risk_amount:.2f}, Quantity: {quantity}, "
            f"Stop distance: {data.atr * self.config.atr_stop_multiplier:.2f}"
        )

        # Open position
        result = open_position(self.client, symbol, signal, quantity, self.config)

        if result:
            # Save state
            self.position_states[symbol] = PositionState(
                symbol=symbol,
                side=signal,
                entry_price=result["avg_price"],
                quantity=quantity,
                pyramid_count=0,
                last_pyramid_price=result["avg_price"],
                atr_at_entry=data.atr
            )
            save_state(self.position_states)

    def run_once(self) -> None:
        """Run one iteration of the strategy."""
        logger.info("=" * 60)
        logger.info(f"Strategy check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Get balance
        balance = get_usdt_balance(self.client)
        available = get_available_balance(self.client)

        logger.info(f"Balance: ${balance:.2f} USDT (Available: ${available:.2f})")

        # Check minimum balance
        if balance < self.config.min_balance_for_trading:
            logger.warning(
                f"Balance ${balance:.2f} below minimum ${self.config.min_balance_for_trading}. "
                "Bot paused."
            )
            return

        # Process each symbol
        for symbol in self.config.symbols:
            try:
                self.process_symbol(symbol, balance)
            except Exception as e:
                logger.error(f"{symbol}: Unexpected error: {e}")

        logger.info("=" * 60)

    def run(self) -> None:
        """Run the strategy loop forever."""
        self.running = True
        logger.info("Starting strategy loop...")

        while self.running:
            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")

            if self.running:
                logger.info(f"Sleeping for {self.config.check_interval_seconds} seconds...")
                time.sleep(self.config.check_interval_seconds)

        logger.info("Strategy stopped.")

    def stop(self) -> None:
        """Stop the strategy loop."""
        self.running = False


# ==================== CLI Entry Point ====================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Donchian Breakout Trading Strategy")
    parser.add_argument("--api-key", required=True, help="Binance API key")
    parser.add_argument("--api-secret", required=True, help="Binance API secret")
    parser.add_argument("--testnet", action="store_true", help="Use testnet")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        help="Symbols to trade"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Check interval in seconds (default: 1800 = 30 min)"
    )

    args = parser.parse_args()

    # Create config
    config = StrategyConfig(
        symbols=args.symbols,
        check_interval_seconds=args.interval
    )

    # Create and run strategy
    strategy = DonchianBreakoutStrategy(
        api_key=args.api_key,
        api_secret=args.api_secret,
        config=config,
        testnet=args.testnet
    )

    if args.once:
        strategy.run_once()
    else:
        strategy.run()


if __name__ == "__main__":
    main()
