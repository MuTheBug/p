"""
Trendline Trading Strategy Bot

Implements the Trendline Strategy for swing trading on Binance Futures:
- Trendline Bounce: Enter when price touches and respects a trendline
- Trendline Break (2-point): Enter on break of 2-touchpoint trendline
- Trendline Break (3-point): Enter on break of 3+ touchpoint trendline

Features:
- Automatic trendline detection from price data
- Action Line and Safety Line management
- Trailing stop along trendlines
- Position sizing based on risk
- Telegram notifications for all trade events

Based on the Tori Trades Trendline Strategy from TradeZella.
"""

import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
from collections import deque

from binance_futures import (
    BinanceFuturesClient,
    OrderSide,
    OrderType,
    PositionSide,
    MarginType,
    WorkingType,
    OrderResult,
    AlgoOrderResult,
    BinanceFuturesError
)
from telegram_notifier import TelegramNotifier


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """Trend direction enumeration."""
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"


class SetupType(Enum):
    """Trading setup types."""
    TRENDLINE_BOUNCE = "TRENDLINE_BOUNCE"
    TRENDLINE_BREAK_2PT = "TRENDLINE_BREAK_2PT"
    TRENDLINE_BREAK_3PT = "TRENDLINE_BREAK_3PT"


class TradeStatus(Enum):
    """Trade status enumeration."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


@dataclass
class Trendline:
    """Trendline data structure."""
    start_time: int  # Timestamp of first touchpoint
    start_price: float
    end_time: int  # Timestamp of last touchpoint
    end_price: float
    touchpoints: List[Tuple[int, float]]  # List of (timestamp, price) touchpoints
    direction: TrendDirection
    slope: float
    is_valid: bool = True

    @property
    def num_touchpoints(self) -> int:
        return len(self.touchpoints)

    def get_price_at_time(self, timestamp: int) -> float:
        """Calculate trendline price at a given timestamp."""
        time_diff = timestamp - self.start_time
        return self.start_price + (self.slope * time_diff)

    def time_span_hours(self) -> float:
        """Get time span in hours between first and last touchpoint."""
        return (self.end_time - self.start_time) / (1000 * 3600)


@dataclass
class TradeSetup:
    """Trading setup data structure."""
    setup_type: SetupType
    symbol: str
    direction: str  # "LONG" or "SHORT"
    action_line: Trendline  # Entry signal line
    safety_line: Optional[Trendline]  # Risk management line
    entry_price: float
    stop_loss_price: float
    suggested_quantity: float
    timestamp: int
    confidence: float = 0.0  # 0-1 confidence score
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveTrade:
    """Active trade tracking."""
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_time: datetime
    stop_loss_price: float
    take_profit_price: Optional[float]
    setup_type: SetupType
    action_line: Trendline
    safety_line: Optional[Trendline]
    status: TradeStatus = TradeStatus.OPEN
    order_ids: List[int] = field(default_factory=list)
    algo_ids: List[int] = field(default_factory=list)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None


class TrendlineDetector:
    """
    Automatic trendline detection from price data.

    Uses pivot point detection and linear regression to identify
    significant trendlines with multiple touchpoints.
    """

    def __init__(
        self,
        pivot_lookback: int = 5,
        min_touchpoints: int = 2,
        price_tolerance_pct: float = 0.5,
        min_time_span_hours: float = 168  # 1 week minimum
    ):
        """
        Initialize trendline detector.

        Args:
            pivot_lookback: Bars to look back for pivot detection
            min_touchpoints: Minimum touchpoints for valid trendline
            price_tolerance_pct: Price tolerance for touchpoint detection (%)
            min_time_span_hours: Minimum hours between first touchpoint and current
        """
        self.pivot_lookback = pivot_lookback
        self.min_touchpoints = min_touchpoints
        self.price_tolerance_pct = price_tolerance_pct
        self.min_time_span_hours = min_time_span_hours

    def find_pivot_highs(
        self,
        highs: np.ndarray,
        times: np.ndarray
    ) -> List[Tuple[int, float]]:
        """Find pivot high points in price data."""
        pivots = []
        for i in range(self.pivot_lookback, len(highs) - self.pivot_lookback):
            is_pivot = True
            for j in range(1, self.pivot_lookback + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append((int(times[i]), float(highs[i])))
        return pivots

    def find_pivot_lows(
        self,
        lows: np.ndarray,
        times: np.ndarray
    ) -> List[Tuple[int, float]]:
        """Find pivot low points in price data."""
        pivots = []
        for i in range(self.pivot_lookback, len(lows) - self.pivot_lookback):
            is_pivot = True
            for j in range(1, self.pivot_lookback + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_pivot = False
                    break
            if is_pivot:
                pivots.append((int(times[i]), float(lows[i])))
        return pivots

    def _fit_trendline(
        self,
        points: List[Tuple[int, float]]
    ) -> Tuple[float, float]:
        """Fit a linear trendline through points using least squares."""
        if len(points) < 2:
            return 0.0, 0.0

        times = np.array([p[0] for p in points], dtype=np.float64)
        prices = np.array([p[1] for p in points], dtype=np.float64)

        # Normalize times to avoid numerical issues
        times_normalized = times - times[0]

        # Linear regression: price = slope * time + intercept
        A = np.vstack([times_normalized, np.ones(len(times_normalized))]).T
        slope, intercept = np.linalg.lstsq(A, prices, rcond=None)[0]

        return slope, intercept

    def _count_touchpoints(
        self,
        slope: float,
        intercept: float,
        start_time: int,
        candidate_points: List[Tuple[int, float]],
        tolerance_pct: float
    ) -> List[Tuple[int, float]]:
        """Count how many points touch the trendline within tolerance."""
        touchpoints = []
        for time, price in candidate_points:
            time_diff = time - start_time
            expected_price = intercept + slope * time_diff
            tolerance = expected_price * (tolerance_pct / 100)

            if abs(price - expected_price) <= tolerance:
                touchpoints.append((time, price))

        return touchpoints

    def detect_uptrend_lines(
        self,
        klines: List[Dict[str, Any]],
        current_time: int
    ) -> List[Trendline]:
        """
        Detect uptrend support trendlines from kline data.

        Args:
            klines: List of kline dictionaries with OHLCV data
            current_time: Current timestamp in milliseconds

        Returns:
            List of detected uptrend trendlines
        """
        if len(klines) < self.pivot_lookback * 2 + 1:
            return []

        lows = np.array([float(k['low']) for k in klines])
        times = np.array([int(k['time']) for k in klines])

        pivot_lows = self.find_pivot_lows(lows, times)

        if len(pivot_lows) < self.min_touchpoints:
            return []

        trendlines = []

        # Try different combinations of pivot points
        for i in range(len(pivot_lows)):
            for j in range(i + 1, len(pivot_lows)):
                p1 = pivot_lows[i]
                p2 = pivot_lows[j]

                # Must be ascending (uptrend)
                if p2[1] <= p1[1]:
                    continue

                # Calculate slope
                time_diff = p2[0] - p1[0]
                if time_diff == 0:
                    continue

                slope = (p2[1] - p1[1]) / time_diff

                # Must be positive slope for uptrend
                if slope <= 0:
                    continue

                # Find all touchpoints
                touchpoints = self._count_touchpoints(
                    slope, p1[1], p1[0],
                    pivot_lows[i:],
                    self.price_tolerance_pct
                )

                if len(touchpoints) < self.min_touchpoints:
                    continue

                # Check time span requirement
                time_span_hours = (current_time - p1[0]) / (1000 * 3600)
                if time_span_hours < self.min_time_span_hours:
                    continue

                trendline = Trendline(
                    start_time=touchpoints[0][0],
                    start_price=touchpoints[0][1],
                    end_time=touchpoints[-1][0],
                    end_price=touchpoints[-1][1],
                    touchpoints=touchpoints,
                    direction=TrendDirection.UPTREND,
                    slope=slope,
                    is_valid=True
                )
                trendlines.append(trendline)

        # Sort by number of touchpoints (more touchpoints = stronger)
        trendlines.sort(key=lambda x: x.num_touchpoints, reverse=True)

        return trendlines

    def detect_downtrend_lines(
        self,
        klines: List[Dict[str, Any]],
        current_time: int
    ) -> List[Trendline]:
        """
        Detect downtrend resistance trendlines from kline data.

        Args:
            klines: List of kline dictionaries with OHLCV data
            current_time: Current timestamp in milliseconds

        Returns:
            List of detected downtrend trendlines
        """
        if len(klines) < self.pivot_lookback * 2 + 1:
            return []

        highs = np.array([float(k['high']) for k in klines])
        times = np.array([int(k['time']) for k in klines])

        pivot_highs = self.find_pivot_highs(highs, times)

        if len(pivot_highs) < self.min_touchpoints:
            return []

        trendlines = []

        for i in range(len(pivot_highs)):
            for j in range(i + 1, len(pivot_highs)):
                p1 = pivot_highs[i]
                p2 = pivot_highs[j]

                # Must be descending (downtrend)
                if p2[1] >= p1[1]:
                    continue

                time_diff = p2[0] - p1[0]
                if time_diff == 0:
                    continue

                slope = (p2[1] - p1[1]) / time_diff

                # Must be negative slope for downtrend
                if slope >= 0:
                    continue

                touchpoints = self._count_touchpoints(
                    slope, p1[1], p1[0],
                    pivot_highs[i:],
                    self.price_tolerance_pct
                )

                if len(touchpoints) < self.min_touchpoints:
                    continue

                time_span_hours = (current_time - p1[0]) / (1000 * 3600)
                if time_span_hours < self.min_time_span_hours:
                    continue

                trendline = Trendline(
                    start_time=touchpoints[0][0],
                    start_price=touchpoints[0][1],
                    end_time=touchpoints[-1][0],
                    end_price=touchpoints[-1][1],
                    touchpoints=touchpoints,
                    direction=TrendDirection.DOWNTREND,
                    slope=slope,
                    is_valid=True
                )
                trendlines.append(trendline)

        trendlines.sort(key=lambda x: x.num_touchpoints, reverse=True)

        return trendlines


class TrendlineStrategyBot:
    """
    Trendline Strategy Trading Bot.

    Implements the complete Trendline Strategy including:
    - Trendline Bounce setups
    - Trendline Break setups (2-point and 3-point)
    - Action Line and Safety Line management
    - Trailing stops along trendlines
    - Risk-based position sizing
    - Telegram notifications

    Args:
        binance_client: BinanceFuturesClient instance
        telegram_notifier: TelegramNotifier instance (optional)
        config: Bot configuration dictionary

    Example:
        >>> from binance_futures import BinanceFuturesClient
        >>> from telegram_notifier import TelegramNotifier
        >>>
        >>> client = BinanceFuturesClient(api_key, api_secret, testnet=True)
        >>> notifier = TelegramNotifier(bot_token, chat_id)
        >>>
        >>> bot = TrendlineStrategyBot(client, notifier)
        >>> bot.run(symbols=["BTCUSDT", "ETHUSDT"])
    """

    def __init__(
        self,
        binance_client: BinanceFuturesClient,
        telegram_notifier: Optional[TelegramNotifier] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.client = binance_client
        self.notifier = telegram_notifier
        self.config = config or self._default_config()

        # Initialize components
        self.detector = TrendlineDetector(
            pivot_lookback=self.config.get("pivot_lookback", 5),
            min_touchpoints=self.config.get("min_touchpoints", 2),
            price_tolerance_pct=self.config.get("price_tolerance_pct", 0.5),
            min_time_span_hours=self.config.get("min_time_span_hours", 168)
        )

        # Trading state
        self.active_trades: Dict[str, ActiveTrade] = {}
        self.detected_setups: Dict[str, List[TradeSetup]] = {}
        self.trendlines_cache: Dict[str, Dict[str, List[Trendline]]] = {}

        # Runtime control
        self._running = False
        self._last_check: Dict[str, int] = {}

    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            # Trendline detection
            "pivot_lookback": 5,
            "min_touchpoints": 2,
            "price_tolerance_pct": 0.5,
            "min_time_span_hours": 168,  # 1 week

            # Timeframe
            "timeframe": "4h",
            "kline_limit": 500,

            # Risk management
            "risk_per_trade_pct": 1.0,  # Risk 1% per trade
            "max_positions": 3,
            "leverage": 10,
            "use_isolated_margin": True,

            # Entry settings
            "entry_buffer_pct": 0.1,  # Enter slightly before trendline
            "stop_loss_buffer_pct": 0.5,  # Stop loss buffer beyond line

            # Setup preferences
            "enable_bounce_setups": True,
            "enable_break_2pt_setups": True,
            "enable_break_3pt_setups": True,
            "min_confidence": 0.6,

            # Trailing stop
            "enable_trailing_stop": True,
            "trail_update_interval_hours": 4,

            # Monitoring
            "check_interval_seconds": 60,
            "price_near_line_pct": 1.0,  # Price within 1% of trendline

            # Take profit (optional)
            "take_profit_rr_ratio": None,  # e.g., 2.0 for 2:1 RR
        }

    def _notify(
        self,
        method: str,
        **kwargs
    ):
        """Send notification if notifier is configured."""
        if self.notifier is None:
            return

        try:
            func = getattr(self.notifier, method, None)
            if func:
                func(**kwargs)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _get_klines(
        self,
        symbol: str,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Fetch kline data for symbol."""
        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=self.config["timeframe"],
                limit=limit
            )

            # Convert to standardized format
            formatted = []
            for k in klines:
                formatted.append({
                    "time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6]
                })
            return formatted

        except BinanceFuturesError as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            return []

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol."""
        try:
            ticker = self.client.get_ticker_price(symbol)
            return float(ticker.get("price", 0))
        except BinanceFuturesError as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None

    def _calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float
    ) -> float:
        """
        Calculate position size based on risk parameters.

        Uses fixed percentage risk per trade.
        """
        try:
            account = self.client.get_account()
            balance = float(account.get("totalWalletBalance", 0))

            risk_amount = balance * (self.config["risk_per_trade_pct"] / 100)
            price_risk = abs(entry_price - stop_loss_price)

            if price_risk == 0:
                return 0

            position_size = risk_amount / price_risk

            # Round to symbol precision
            position_size = self.client.round_quantity(symbol, position_size)

            return position_size

        except BinanceFuturesError as e:
            logger.error(f"Failed to calculate position size: {e}")
            return 0

    def detect_bounce_setup(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_price: float,
        current_time: int
    ) -> Optional[TradeSetup]:
        """
        Detect trendline bounce setup.

        For bounce setups:
        - Action Line = Safety Line (same trendline)
        - Enter when price touches the trendline
        - Exit if price closes through the line
        """
        # Detect uptrend lines (support - for long entries)
        uptrend_lines = self.detector.detect_uptrend_lines(klines, current_time)

        for trendline in uptrend_lines:
            if trendline.num_touchpoints < 2:
                continue

            # Calculate expected trendline price at current time
            trendline_price = trendline.get_price_at_time(current_time)

            # Check if price is near the trendline (potential bounce)
            price_diff_pct = abs(current_price - trendline_price) / trendline_price * 100

            if price_diff_pct <= self.config["price_near_line_pct"]:
                # Potential bounce setup - price is testing the trendline
                if current_price >= trendline_price:
                    # Price is at or slightly above the uptrend line
                    entry_price = trendline_price * (1 + self.config["entry_buffer_pct"] / 100)
                    stop_loss = trendline_price * (1 - self.config["stop_loss_buffer_pct"] / 100)

                    quantity = self._calculate_position_size(symbol, entry_price, stop_loss)

                    if quantity <= 0:
                        continue

                    confidence = min(trendline.num_touchpoints / 5.0, 1.0)

                    setup = TradeSetup(
                        setup_type=SetupType.TRENDLINE_BOUNCE,
                        symbol=symbol,
                        direction="LONG",
                        action_line=trendline,
                        safety_line=trendline,  # Same line for bounce
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        suggested_quantity=quantity,
                        timestamp=current_time,
                        confidence=confidence,
                        additional_info={
                            "touchpoints": trendline.num_touchpoints,
                            "time_span_hours": trendline.time_span_hours(),
                            "trendline_price": trendline_price,
                            "price_diff_pct": price_diff_pct
                        }
                    )

                    if setup.confidence >= self.config["min_confidence"]:
                        return setup

        # Detect downtrend lines (resistance - for short entries on bounce)
        downtrend_lines = self.detector.detect_downtrend_lines(klines, current_time)

        for trendline in downtrend_lines:
            if trendline.num_touchpoints < 2:
                continue

            trendline_price = trendline.get_price_at_time(current_time)
            price_diff_pct = abs(current_price - trendline_price) / trendline_price * 100

            if price_diff_pct <= self.config["price_near_line_pct"]:
                if current_price <= trendline_price:
                    # Price is at or slightly below the downtrend line
                    entry_price = trendline_price * (1 - self.config["entry_buffer_pct"] / 100)
                    stop_loss = trendline_price * (1 + self.config["stop_loss_buffer_pct"] / 100)

                    quantity = self._calculate_position_size(symbol, entry_price, stop_loss)

                    if quantity <= 0:
                        continue

                    confidence = min(trendline.num_touchpoints / 5.0, 1.0)

                    setup = TradeSetup(
                        setup_type=SetupType.TRENDLINE_BOUNCE,
                        symbol=symbol,
                        direction="SHORT",
                        action_line=trendline,
                        safety_line=trendline,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        suggested_quantity=quantity,
                        timestamp=current_time,
                        confidence=confidence,
                        additional_info={
                            "touchpoints": trendline.num_touchpoints,
                            "time_span_hours": trendline.time_span_hours(),
                            "trendline_price": trendline_price,
                            "price_diff_pct": price_diff_pct
                        }
                    )

                    if setup.confidence >= self.config["min_confidence"]:
                        return setup

        return None

    def detect_break_setup(
        self,
        symbol: str,
        klines: List[Dict[str, Any]],
        current_price: float,
        current_time: int
    ) -> Optional[TradeSetup]:
        """
        Detect trendline break setup.

        For break setups:
        - Action Line = The broken trendline
        - Safety Line = Opposing trendline for risk control
        - 2-touchpoint breaks are valid but less reliable
        - 3+ touchpoint breaks are more reliable
        """
        # Look for downtrend break (bullish - go long)
        downtrend_lines = self.detector.detect_downtrend_lines(klines, current_time)

        for trendline in downtrend_lines:
            trendline_price = trendline.get_price_at_time(current_time)

            # Check if price has broken above the downtrend line
            if current_price > trendline_price:
                break_pct = (current_price - trendline_price) / trendline_price * 100

                # Confirm break (price should be above by a margin)
                if break_pct > 0.2:  # At least 0.2% above for confirmation
                    # Find safety line (uptrend support line)
                    uptrend_lines = self.detector.detect_uptrend_lines(klines, current_time)

                    safety_line = None
                    stop_loss = None

                    if uptrend_lines:
                        # Use the strongest uptrend line as safety
                        safety_line = uptrend_lines[0]
                        stop_loss = safety_line.get_price_at_time(current_time)
                        stop_loss = stop_loss * (1 - self.config["stop_loss_buffer_pct"] / 100)
                    else:
                        # No safety line - use recent swing low
                        recent_lows = [k["low"] for k in klines[-20:]]
                        stop_loss = min(recent_lows) * (1 - self.config["stop_loss_buffer_pct"] / 100)

                    # Check if risk is acceptable (stop not too far)
                    risk_pct = (current_price - stop_loss) / current_price * 100
                    if risk_pct > 5:  # Skip if risk > 5%
                        continue

                    quantity = self._calculate_position_size(symbol, current_price, stop_loss)

                    if quantity <= 0:
                        continue

                    # Determine setup type based on touchpoints
                    if trendline.num_touchpoints >= 3:
                        setup_type = SetupType.TRENDLINE_BREAK_3PT
                        confidence = min(trendline.num_touchpoints / 5.0, 1.0)
                    else:
                        setup_type = SetupType.TRENDLINE_BREAK_2PT
                        confidence = min(trendline.num_touchpoints / 5.0, 0.8)

                    setup = TradeSetup(
                        setup_type=setup_type,
                        symbol=symbol,
                        direction="LONG",
                        action_line=trendline,
                        safety_line=safety_line,
                        entry_price=current_price,
                        stop_loss_price=stop_loss,
                        suggested_quantity=quantity,
                        timestamp=current_time,
                        confidence=confidence,
                        additional_info={
                            "touchpoints": trendline.num_touchpoints,
                            "break_pct": break_pct,
                            "risk_pct": risk_pct,
                            "has_safety_line": safety_line is not None
                        }
                    )

                    if setup.confidence >= self.config["min_confidence"]:
                        return setup

        # Look for uptrend break (bearish - go short)
        uptrend_lines = self.detector.detect_uptrend_lines(klines, current_time)

        for trendline in uptrend_lines:
            trendline_price = trendline.get_price_at_time(current_time)

            if current_price < trendline_price:
                break_pct = (trendline_price - current_price) / trendline_price * 100

                if break_pct > 0.2:
                    downtrend_lines = self.detector.detect_downtrend_lines(klines, current_time)

                    safety_line = None
                    stop_loss = None

                    if downtrend_lines:
                        safety_line = downtrend_lines[0]
                        stop_loss = safety_line.get_price_at_time(current_time)
                        stop_loss = stop_loss * (1 + self.config["stop_loss_buffer_pct"] / 100)
                    else:
                        recent_highs = [k["high"] for k in klines[-20:]]
                        stop_loss = max(recent_highs) * (1 + self.config["stop_loss_buffer_pct"] / 100)

                    risk_pct = (stop_loss - current_price) / current_price * 100
                    if risk_pct > 5:
                        continue

                    quantity = self._calculate_position_size(symbol, current_price, stop_loss)

                    if quantity <= 0:
                        continue

                    if trendline.num_touchpoints >= 3:
                        setup_type = SetupType.TRENDLINE_BREAK_3PT
                        confidence = min(trendline.num_touchpoints / 5.0, 1.0)
                    else:
                        setup_type = SetupType.TRENDLINE_BREAK_2PT
                        confidence = min(trendline.num_touchpoints / 5.0, 0.8)

                    setup = TradeSetup(
                        setup_type=setup_type,
                        symbol=symbol,
                        direction="SHORT",
                        action_line=trendline,
                        safety_line=safety_line,
                        entry_price=current_price,
                        stop_loss_price=stop_loss,
                        suggested_quantity=quantity,
                        timestamp=current_time,
                        confidence=confidence,
                        additional_info={
                            "touchpoints": trendline.num_touchpoints,
                            "break_pct": break_pct,
                            "risk_pct": risk_pct,
                            "has_safety_line": safety_line is not None
                        }
                    )

                    if setup.confidence >= self.config["min_confidence"]:
                        return setup

        return None

    def scan_for_setups(
        self,
        symbol: str
    ) -> List[TradeSetup]:
        """
        Scan for all valid trading setups on a symbol.

        Returns list of detected setups sorted by confidence.
        """
        setups = []

        klines = self._get_klines(symbol, self.config["kline_limit"])
        if not klines:
            return setups

        current_price = self._get_current_price(symbol)
        if current_price is None:
            return setups

        current_time = int(time.time() * 1000)

        # Detect bounce setups
        if self.config["enable_bounce_setups"]:
            bounce_setup = self.detect_bounce_setup(
                symbol, klines, current_price, current_time
            )
            if bounce_setup:
                setups.append(bounce_setup)

        # Detect break setups
        if self.config["enable_break_2pt_setups"] or self.config["enable_break_3pt_setups"]:
            break_setup = self.detect_break_setup(
                symbol, klines, current_price, current_time
            )
            if break_setup:
                if break_setup.setup_type == SetupType.TRENDLINE_BREAK_2PT:
                    if self.config["enable_break_2pt_setups"]:
                        setups.append(break_setup)
                else:
                    if self.config["enable_break_3pt_setups"]:
                        setups.append(break_setup)

        # Sort by confidence
        setups.sort(key=lambda x: x.confidence, reverse=True)

        return setups

    def execute_trade(
        self,
        setup: TradeSetup
    ) -> Optional[ActiveTrade]:
        """
        Execute a trade based on the setup.

        Places entry order and stop loss order.
        """
        symbol = setup.symbol
        side = OrderSide.BUY if setup.direction == "LONG" else OrderSide.SELL

        try:
            # Set leverage
            self.client.set_leverage(symbol, self.config["leverage"])

            # Set margin type
            margin_type = MarginType.ISOLATED if self.config["use_isolated_margin"] else MarginType.CROSSED
            try:
                self.client.set_margin_type(symbol, margin_type)
            except BinanceFuturesError:
                pass  # May already be set

            # Place market entry order
            entry_order = self.client.market_order(
                symbol=symbol,
                side=side,
                quantity=setup.suggested_quantity
            )

            if entry_order.status not in ["FILLED", "NEW"]:
                logger.error(f"Entry order failed: {entry_order.status}")
                return None

            entry_price = float(entry_order.avg_price) if entry_order.avg_price != "0" else setup.entry_price

            # Place stop loss using algo API
            sl_side = OrderSide.SELL if setup.direction == "LONG" else OrderSide.BUY

            stop_order = self.client.algo_stop_market_order(
                symbol=symbol,
                side=sl_side,
                quantity=setup.suggested_quantity,
                stop_price=setup.stop_loss_price,
                working_type=WorkingType.MARK_PRICE
            )

            # Calculate take profit if configured
            take_profit_price = None
            tp_algo_id = None

            if self.config["take_profit_rr_ratio"]:
                risk = abs(entry_price - setup.stop_loss_price)
                if setup.direction == "LONG":
                    take_profit_price = entry_price + (risk * self.config["take_profit_rr_ratio"])
                else:
                    take_profit_price = entry_price - (risk * self.config["take_profit_rr_ratio"])

                take_profit_price = self.client.round_price(symbol, take_profit_price)

                tp_order = self.client.algo_take_profit_market_order(
                    symbol=symbol,
                    side=sl_side,
                    quantity=setup.suggested_quantity,
                    stop_price=take_profit_price,
                    working_type=WorkingType.MARK_PRICE
                )
                tp_algo_id = tp_order.algo_id

            # Create active trade record
            trade_id = f"{symbol}_{int(time.time())}"
            active_trade = ActiveTrade(
                trade_id=trade_id,
                symbol=symbol,
                side=setup.direction,
                quantity=setup.suggested_quantity,
                entry_price=entry_price,
                entry_time=datetime.now(),
                stop_loss_price=setup.stop_loss_price,
                take_profit_price=take_profit_price,
                setup_type=setup.setup_type,
                action_line=setup.action_line,
                safety_line=setup.safety_line,
                status=TradeStatus.OPEN,
                order_ids=[entry_order.order_id],
                algo_ids=[stop_order.algo_id] + ([tp_algo_id] if tp_algo_id else [])
            )

            self.active_trades[trade_id] = active_trade

            # Send notification
            self._notify(
                "send_trade_entry",
                symbol=symbol,
                side=setup.direction,
                quantity=setup.suggested_quantity,
                entry_price=entry_price,
                stop_loss=setup.stop_loss_price,
                take_profit=take_profit_price,
                strategy="Trendline Strategy",
                setup_type=setup.setup_type.value.replace("_", " ").title(),
                leverage=self.config["leverage"],
                additional_info={
                    "Touchpoints": setup.action_line.num_touchpoints,
                    "Confidence": f"{setup.confidence:.0%}",
                    "Time Span": f"{setup.action_line.time_span_hours():.0f}h"
                }
            )

            logger.info(f"Trade executed: {trade_id} - {setup.direction} {symbol}")

            return active_trade

        except BinanceFuturesError as e:
            logger.error(f"Failed to execute trade: {e}")
            self._notify(
                "send_error",
                error_message=str(e),
                context="Trade Execution",
                symbol=symbol
            )
            return None

    def update_trailing_stop(
        self,
        trade: ActiveTrade
    ):
        """
        Update trailing stop based on trendline movement.

        For bounce setups, trail along the action/safety line.
        For break setups, trail along the safety line.
        """
        if not self.config["enable_trailing_stop"]:
            return

        if trade.status != TradeStatus.OPEN:
            return

        current_time = int(time.time() * 1000)

        # Get safety line for stop calculation
        safety_line = trade.safety_line or trade.action_line

        new_stop = safety_line.get_price_at_time(current_time)

        # Add buffer
        if trade.side == "LONG":
            new_stop = new_stop * (1 - self.config["stop_loss_buffer_pct"] / 100)
            # Only move stop up, never down
            if new_stop <= trade.stop_loss_price:
                return
        else:
            new_stop = new_stop * (1 + self.config["stop_loss_buffer_pct"] / 100)
            # Only move stop down, never up
            if new_stop >= trade.stop_loss_price:
                return

        new_stop = self.client.round_price(trade.symbol, new_stop)

        try:
            # Cancel old stop
            for algo_id in trade.algo_ids:
                try:
                    self.client.cancel_algo_order(trade.symbol, algo_id)
                except BinanceFuturesError:
                    pass

            # Place new stop
            sl_side = OrderSide.SELL if trade.side == "LONG" else OrderSide.BUY

            new_stop_order = self.client.algo_stop_market_order(
                symbol=trade.symbol,
                side=sl_side,
                quantity=trade.quantity,
                stop_price=new_stop,
                working_type=WorkingType.MARK_PRICE
            )

            old_stop = trade.stop_loss_price
            trade.stop_loss_price = new_stop
            trade.algo_ids = [new_stop_order.algo_id]

            # Re-add take profit if exists
            if trade.take_profit_price:
                tp_order = self.client.algo_take_profit_market_order(
                    symbol=trade.symbol,
                    side=sl_side,
                    quantity=trade.quantity,
                    stop_price=trade.take_profit_price,
                    working_type=WorkingType.MARK_PRICE
                )
                trade.algo_ids.append(tp_order.algo_id)

            # Notify
            current_price = self._get_current_price(trade.symbol)
            self._notify(
                "send_stop_update",
                symbol=trade.symbol,
                side=trade.side,
                old_stop=old_stop,
                new_stop=new_stop,
                current_price=current_price or 0,
                reason="Trailing along trendline"
            )

            logger.info(f"Updated trailing stop for {trade.trade_id}: {old_stop} -> {new_stop}")

        except BinanceFuturesError as e:
            logger.error(f"Failed to update trailing stop: {e}")

    def check_position_status(
        self,
        trade: ActiveTrade
    ):
        """Check if position is still open or has been closed."""
        try:
            positions = self.client.get_positions(trade.symbol)

            position_open = False
            for pos in positions:
                pos_amt = float(pos.get("positionAmt", 0))
                if abs(pos_amt) > 0:
                    position_open = True
                    break

            if not position_open and trade.status == TradeStatus.OPEN:
                # Position closed - determine reason
                self._handle_trade_close(trade)

        except BinanceFuturesError as e:
            logger.error(f"Failed to check position status: {e}")

    def _handle_trade_close(
        self,
        trade: ActiveTrade
    ):
        """Handle trade closure and send notification."""
        trade.status = TradeStatus.CLOSED
        trade.exit_time = datetime.now()

        # Get exit price from recent trades
        try:
            trades = self.client.get_account_trades(trade.symbol, limit=10)
            if trades:
                latest = trades[-1]
                trade.exit_price = float(latest.get("price", 0))

                # Determine exit reason
                if trade.side == "LONG":
                    if trade.exit_price <= trade.stop_loss_price * 1.01:
                        trade.exit_reason = "Stop Loss"
                    elif trade.take_profit_price and trade.exit_price >= trade.take_profit_price * 0.99:
                        trade.exit_reason = "Take Profit"
                    else:
                        trade.exit_reason = "Manual/Other"
                else:
                    if trade.exit_price >= trade.stop_loss_price * 0.99:
                        trade.exit_reason = "Stop Loss"
                    elif trade.take_profit_price and trade.exit_price <= trade.take_profit_price * 1.01:
                        trade.exit_reason = "Take Profit"
                    else:
                        trade.exit_reason = "Manual/Other"

                # Calculate PnL
                if trade.side == "LONG":
                    trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
                else:
                    trade.pnl = (trade.entry_price - trade.exit_price) * trade.quantity

                pnl_percent = (trade.pnl / (trade.entry_price * trade.quantity)) * 100

                # Calculate duration
                duration = trade.exit_time - trade.entry_time
                duration_str = str(duration).split(".")[0]

                # Send notification
                self._notify(
                    "send_trade_exit",
                    symbol=trade.symbol,
                    side=trade.side,
                    quantity=trade.quantity,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    pnl=trade.pnl,
                    pnl_percent=pnl_percent,
                    exit_reason=trade.exit_reason,
                    strategy="Trendline Strategy",
                    duration=duration_str
                )

                logger.info(
                    f"Trade closed: {trade.trade_id} - "
                    f"PnL: ${trade.pnl:.2f} ({pnl_percent:.2f}%)"
                )

        except BinanceFuturesError as e:
            logger.error(f"Failed to get exit details: {e}")

    def close_trade(
        self,
        trade_id: str,
        reason: str = "Manual"
    ):
        """Manually close a trade."""
        if trade_id not in self.active_trades:
            logger.warning(f"Trade {trade_id} not found")
            return

        trade = self.active_trades[trade_id]

        if trade.status != TradeStatus.OPEN:
            logger.warning(f"Trade {trade_id} is not open")
            return

        try:
            # Cancel all algo orders
            for algo_id in trade.algo_ids:
                try:
                    self.client.cancel_algo_order(trade.symbol, algo_id)
                except BinanceFuturesError:
                    pass

            # Close position with market order
            close_side = OrderSide.SELL if trade.side == "LONG" else OrderSide.BUY

            close_order = self.client.market_order(
                symbol=trade.symbol,
                side=close_side,
                quantity=trade.quantity
            )

            trade.exit_price = float(close_order.avg_price) if close_order.avg_price != "0" else None
            trade.exit_reason = reason

            self._handle_trade_close(trade)

        except BinanceFuturesError as e:
            logger.error(f"Failed to close trade: {e}")
            self._notify(
                "send_error",
                error_message=str(e),
                context="Close Trade",
                symbol=trade.symbol
            )

    def run(
        self,
        symbols: List[str],
        auto_trade: bool = False
    ):
        """
        Run the trading bot.

        Args:
            symbols: List of symbols to monitor
            auto_trade: Automatically execute trades (default: False - signal only)
        """
        self._running = True
        logger.info(f"Starting Trendline Strategy Bot for {symbols}")

        if self.notifier:
            self.notifier.send_custom(
                title="BOT STARTED",
                body=f"<b>Monitoring:</b> {', '.join(symbols)}\n"
                     f"<b>Auto-trade:</b> {'Enabled' if auto_trade else 'Disabled'}\n"
                     f"<b>Timeframe:</b> {self.config['timeframe']}\n"
                     f"<b>Risk per trade:</b> {self.config['risk_per_trade_pct']}%",
                emoji="🤖"
            )

        while self._running:
            try:
                # Check open positions
                open_trades = [t for t in self.active_trades.values() if t.status == TradeStatus.OPEN]
                for trade in open_trades:
                    self.check_position_status(trade)
                    if trade.status == TradeStatus.OPEN:
                        self.update_trailing_stop(trade)

                # Scan for new setups if not at max positions
                if len(open_trades) < self.config["max_positions"]:
                    for symbol in symbols:
                        # Skip if already have position in this symbol
                        if any(t.symbol == symbol for t in open_trades):
                            continue

                        setups = self.scan_for_setups(symbol)

                        for setup in setups:
                            logger.info(
                                f"Setup detected: {setup.setup_type.value} "
                                f"{setup.direction} {symbol} @ {setup.entry_price:.2f}"
                            )

                            # Send signal notification
                            self._notify(
                                "send_signal_alert",
                                symbol=symbol,
                                signal_type=setup.setup_type.value.replace("_", " ").title(),
                                direction=setup.direction,
                                price=setup.entry_price,
                                strategy="Trendline Strategy",
                                setup_details={
                                    "Stop Loss": f"${setup.stop_loss_price:,.2f}",
                                    "Touchpoints": setup.action_line.num_touchpoints,
                                    "Confidence": f"{setup.confidence:.0%}",
                                    "Quantity": setup.suggested_quantity
                                },
                                action_required=not auto_trade
                            )

                            if auto_trade:
                                self.execute_trade(setup)
                                break  # Only one trade per symbol per cycle

                # Sleep between checks
                time.sleep(self.config["check_interval_seconds"])

            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                self._running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self._notify(
                    "send_error",
                    error_message=str(e),
                    context="Main Loop"
                )
                time.sleep(60)  # Wait before retrying

        if self.notifier:
            self.notifier.send_custom(
                title="BOT STOPPED",
                body="Trendline Strategy Bot has been stopped.",
                emoji="🛑"
            )

    def stop(self):
        """Stop the bot gracefully."""
        self._running = False
        if self.notifier:
            self.notifier.stop()


# Example usage
if __name__ == "__main__":
    import os

    # Configuration
    API_KEY = os.getenv("BINANCE_API_KEY", "your_api_key")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "your_api_secret")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "your_chat_id")

    # Initialize clients
    binance_client = BinanceFuturesClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=True  # Use testnet for testing!
    )

    telegram_notifier = TelegramNotifier(
        bot_token=TELEGRAM_TOKEN,
        chat_id=TELEGRAM_CHAT_ID
    )

    # Custom configuration
    config = {
        "timeframe": "4h",
        "risk_per_trade_pct": 1.0,
        "max_positions": 3,
        "leverage": 10,
        "enable_bounce_setups": True,
        "enable_break_2pt_setups": True,
        "enable_break_3pt_setups": True,
        "min_confidence": 0.6,
        "enable_trailing_stop": True,
        "take_profit_rr_ratio": 2.0,  # 2:1 risk-reward
    }

    # Create and run bot
    bot = TrendlineStrategyBot(
        binance_client=binance_client,
        telegram_notifier=telegram_notifier,
        config=config
    )

    # Run with signal-only mode (no auto-trading)
    # Set auto_trade=True to enable automatic trading
    bot.run(
        symbols=["BTCUSDT", "ETHUSDT"],
        auto_trade=False
    )
