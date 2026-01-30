"""
ML-Based Day Trading Strategy Bot

A highly effective day trading bot using machine learning for signal generation.
Combines technical analysis features with ensemble ML models for robust predictions.

Features:
- Automatic model training on historical data
- Real-time signal generation
- Dynamic position sizing based on confidence
- Risk management with stop loss and take profit
- Telegram notifications for all trade events
"""

import time
import logging
import threading
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import json

from binance_futures import (
    BinanceFuturesClient,
    OrderSide,
    PositionSide,
    MarginType,
    WorkingType,
    OrderResult,
    AlgoOrderResult,
    BinanceFuturesError
)
from telegram_notifier import TelegramNotifier
from ml_features import FeatureEngineer, FeatureSet
from ml_model import TradingModel, ModelConfig, Prediction


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TradeStatus:
    """Trade status enumeration."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class ActiveTrade:
    """Active trade tracking."""
    trade_id: str
    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    confidence: float
    prediction: Prediction
    status: str = "OPEN"
    order_ids: List[int] = field(default_factory=list)
    algo_ids: List[int] = field(default_factory=list)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None


@dataclass
class BotConfig:
    """Configuration for ML trading bot."""
    # Trading symbols
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])

    # Timeframe settings
    timeframe: str = "15m"  # Day trading timeframe
    kline_limit: int = 500  # Historical bars for feature calculation
    training_days: int = 60  # Days of history for training

    # Model settings
    model_retrain_hours: int = 24  # Retrain model every N hours
    min_training_samples: int = 1000
    sequence_length: int = 60
    signal_threshold: float = 0.6
    min_confidence: float = 0.55

    # Risk management
    risk_per_trade_pct: float = 1.0  # % of account per trade
    max_positions: int = 3
    max_position_per_symbol: int = 1
    leverage: int = 10
    use_isolated_margin: bool = True

    # Stop loss and take profit
    stop_loss_pct: float = 1.5  # % from entry
    take_profit_pct: float = 3.0  # % from entry (2:1 R:R)
    use_atr_stops: bool = True  # Use ATR for dynamic stops
    atr_stop_multiplier: float = 2.0
    atr_tp_multiplier: float = 4.0

    # Position sizing
    use_kelly_sizing: bool = False  # Kelly criterion for position sizing
    max_kelly_fraction: float = 0.25  # Max 25% of Kelly

    # Trading hours (UTC) - optional
    trading_start_hour: Optional[int] = None
    trading_end_hour: Optional[int] = None

    # Monitoring
    scan_interval_seconds: int = 60
    price_update_interval: int = 5

    # Model path
    model_path: str = "models"


class MLTradingBot:
    """
    ML-Based Day Trading Bot.

    Uses ensemble machine learning (XGBoost + LSTM) for signal generation
    with comprehensive risk management and position sizing.

    The bot:
    1. Trains on historical data automatically
    2. Scans symbols for trading opportunities
    3. Executes trades with proper risk management
    4. Sends notifications via Telegram
    """

    def __init__(
        self,
        binance_client: BinanceFuturesClient,
        telegram_notifier: Optional[TelegramNotifier] = None,
        config: Optional[BotConfig] = None
    ):
        self.client = binance_client
        self.notifier = telegram_notifier
        self.config = config or BotConfig()

        # Initialize components
        self.feature_engineer = FeatureEngineer()
        self.model = TradingModel(ModelConfig(
            signal_threshold=self.config.signal_threshold,
            min_confidence=self.config.min_confidence,
            lstm_sequence_length=self.config.sequence_length
        ))

        # Trading state
        self.active_trades: Dict[str, ActiveTrade] = {}
        self.symbol_data: Dict[str, Dict[str, Any]] = {}
        self.last_predictions: Dict[str, Prediction] = {}
        self.model_trained_at: Optional[datetime] = None

        # Performance tracking
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_pnl: float = 0
        self.total_trades: int = 0
        self.winning_trades: int = 0

        # Runtime control
        self._running = False
        self._lock = threading.Lock()

    def _notify(self, method: str, **kwargs):
        """Send notification if notifier is configured."""
        if self.notifier is None:
            return
        try:
            func = getattr(self.notifier, method, None)
            if func:
                func(**kwargs)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    def _get_historical_klines(
        self,
        symbol: str,
        days: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch historical kline data for training."""
        days = days or self.config.training_days
        limit = min(1500, days * 96)  # ~96 15m bars per day

        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=self.config.timeframe,
                limit=limit
            )

            formatted = []
            for k in klines:
                formatted.append({
                    'time': int(k[0]),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
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

    def _prepare_training_data(
        self,
        symbols: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Prepare training data from multiple symbols."""
        all_features = []
        all_labels = []

        for symbol in symbols:
            logger.info(f"Fetching data for {symbol}...")
            klines = self._get_historical_klines(symbol)

            if len(klines) < 200:
                logger.warning(f"Insufficient data for {symbol}")
                continue

            # Extract arrays
            open_ = np.array([k['open'] for k in klines])
            high = np.array([k['high'] for k in klines])
            low = np.array([k['low'] for k in klines])
            close = np.array([k['close'] for k in klines])
            volume = np.array([k['volume'] for k in klines])
            times = np.array([k['time'] for k in klines])

            # Extract features
            feature_set = self.feature_engineer.extract_features(
                open_, high, low, close, volume, times
            )

            # Create labels
            labels = self.feature_engineer.create_labels(
                close,
                forward_period=self.model.config.forward_period,
                threshold=self.model.config.label_threshold
            )

            all_features.append(feature_set.features)
            all_labels.append(labels)

        if not all_features:
            raise ValueError("No training data available")

        # Combine all data
        X = np.vstack(all_features)
        y = np.concatenate(all_labels)

        return X, y, self.feature_engineer.feature_names

    def train_model(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Train or retrain the ML model."""
        symbols = symbols or self.config.symbols

        logger.info("Starting model training...")
        self._notify("send_custom",
            title="MODEL TRAINING",
            body=f"Training on {len(symbols)} symbols...",
            emoji="🧠"
        )

        try:
            X, y, feature_names = self._prepare_training_data(symbols)

            logger.info(f"Training data: {X.shape[0]} samples, {X.shape[1]} features")

            metrics = self.model.train(X, y, feature_names)

            self.model_trained_at = datetime.now()

            # Save model
            model_path = Path(self.config.model_path)
            model_path.mkdir(parents=True, exist_ok=True)
            self.model.save(str(model_path))

            self._notify("send_custom",
                title="MODEL TRAINED",
                body=f"<b>Samples:</b> {metrics['total_samples']}\n"
                     f"<b>XGB Accuracy:</b> {metrics.get('xgb_accuracy', 0):.2%}\n"
                     f"<b>LSTM Accuracy:</b> {metrics.get('lstm_accuracy', 0):.2%}",
                emoji="✅"
            )

            return metrics

        except Exception as e:
            logger.error(f"Training failed: {e}")
            self._notify("send_error",
                error_message=str(e),
                context="Model Training"
            )
            raise

    def _calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        confidence: float = 1.0
    ) -> float:
        """Calculate position size based on risk."""
        try:
            account = self.client.get_account()
            balance = float(account.get("totalWalletBalance", 0))

            risk_amount = balance * (self.config.risk_per_trade_pct / 100)

            # Adjust by confidence if using Kelly-like sizing
            if self.config.use_kelly_sizing:
                # Simplified Kelly: f = (p * b - q) / b
                # where p = win prob (confidence), b = win/loss ratio
                win_loss_ratio = self.config.take_profit_pct / self.config.stop_loss_pct
                kelly_fraction = (confidence * win_loss_ratio - (1 - confidence)) / win_loss_ratio
                kelly_fraction = max(0, min(kelly_fraction, self.config.max_kelly_fraction))
                risk_amount *= kelly_fraction / self.config.max_kelly_fraction

            price_risk = abs(entry_price - stop_loss)
            if price_risk == 0:
                return 0

            position_size = risk_amount / price_risk
            position_size = self.client.round_quantity(symbol, position_size)

            return position_size

        except BinanceFuturesError as e:
            logger.error(f"Position size calculation failed: {e}")
            return 0

    def _calculate_stops(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        klines: List[Dict[str, Any]] = None
    ) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels."""
        if self.config.use_atr_stops and klines and len(klines) >= 14:
            # Use ATR for dynamic stops
            high = np.array([k['high'] for k in klines[-20:]])
            low = np.array([k['low'] for k in klines[-20:]])
            close = np.array([k['close'] for k in klines[-20:]])

            atr = self.feature_engineer.atr(high, low, close, 14)[-1]

            if not np.isnan(atr):
                if side == "LONG":
                    stop_loss = entry_price - (atr * self.config.atr_stop_multiplier)
                    take_profit = entry_price + (atr * self.config.atr_tp_multiplier)
                else:
                    stop_loss = entry_price + (atr * self.config.atr_stop_multiplier)
                    take_profit = entry_price - (atr * self.config.atr_tp_multiplier)

                stop_loss = self.client.round_price(symbol, stop_loss)
                take_profit = self.client.round_price(symbol, take_profit)

                return stop_loss, take_profit

        # Fallback to percentage-based stops
        if side == "LONG":
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)

        stop_loss = self.client.round_price(symbol, stop_loss)
        take_profit = self.client.round_price(symbol, take_profit)

        return stop_loss, take_profit

    def _is_trading_hours(self) -> bool:
        """Check if within trading hours."""
        if self.config.trading_start_hour is None:
            return True

        now = datetime.utcnow()
        hour = now.hour

        if self.config.trading_end_hour > self.config.trading_start_hour:
            return self.config.trading_start_hour <= hour < self.config.trading_end_hour
        else:
            # Crosses midnight
            return hour >= self.config.trading_start_hour or hour < self.config.trading_end_hour

    def scan_symbol(self, symbol: str) -> Optional[Prediction]:
        """Scan a symbol for trading opportunity."""
        try:
            klines = self._get_historical_klines(symbol, days=30)

            if len(klines) < 200:
                return None

            # Extract arrays
            open_ = np.array([k['open'] for k in klines])
            high = np.array([k['high'] for k in klines])
            low = np.array([k['low'] for k in klines])
            close = np.array([k['close'] for k in klines])
            volume = np.array([k['volume'] for k in klines])
            times = np.array([k['time'] for k in klines])

            # Extract features
            feature_set = self.feature_engineer.extract_features(
                open_, high, low, close, volume, times
            )

            # Get latest features
            latest_features = feature_set.features[-1]

            # Prepare sequence for LSTM
            seq_len = self.config.sequence_length
            if len(feature_set.features) >= seq_len:
                sequence = feature_set.features[-seq_len:]
            else:
                sequence = None

            # Generate prediction
            prediction = self.model.predict(latest_features, sequence)

            # Store for reference
            self.last_predictions[symbol] = prediction
            self.symbol_data[symbol] = {
                'klines': klines,
                'features': feature_set,
                'current_price': close[-1]
            }

            return prediction

        except Exception as e:
            logger.error(f"Scan failed for {symbol}: {e}")
            return None

    def execute_trade(
        self,
        symbol: str,
        prediction: Prediction
    ) -> Optional[ActiveTrade]:
        """Execute a trade based on prediction."""
        side = "LONG" if prediction.signal == 1 else "SHORT"

        try:
            current_price = self._get_current_price(symbol)
            if current_price is None:
                return None

            # Get klines for ATR calculation
            klines = self.symbol_data.get(symbol, {}).get('klines', [])

            # Calculate stops
            stop_loss, take_profit = self._calculate_stops(
                symbol, current_price, side, klines
            )

            # Calculate position size
            quantity = self._calculate_position_size(
                symbol, current_price, stop_loss, prediction.confidence
            )

            if quantity <= 0:
                logger.warning(f"Position size too small for {symbol}")
                return None

            # Set leverage
            self.client.set_leverage(symbol, self.config.leverage)

            # Set margin type
            margin_type = MarginType.ISOLATED if self.config.use_isolated_margin else MarginType.CROSSED
            try:
                self.client.set_margin_type(symbol, margin_type)
            except BinanceFuturesError:
                pass

            # Place entry order
            order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL
            entry_order = self.client.market_order(
                symbol=symbol,
                side=order_side,
                quantity=quantity
            )

            if entry_order.status not in ["FILLED", "NEW"]:
                logger.error(f"Entry order failed: {entry_order.status}")
                return None

            entry_price = float(entry_order.avg_price) if entry_order.avg_price != "0" else current_price

            # Place stop loss
            sl_side = OrderSide.SELL if side == "LONG" else OrderSide.BUY
            stop_order = self.client.algo_stop_market_order(
                symbol=symbol,
                side=sl_side,
                quantity=quantity,
                stop_price=stop_loss,
                working_type=WorkingType.MARK_PRICE
            )

            # Place take profit
            tp_order = self.client.algo_take_profit_market_order(
                symbol=symbol,
                side=sl_side,
                quantity=quantity,
                stop_price=take_profit,
                working_type=WorkingType.MARK_PRICE
            )

            # Create trade record
            trade_id = f"{symbol}_{int(time.time())}"
            trade = ActiveTrade(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                entry_time=datetime.now(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=prediction.confidence,
                prediction=prediction,
                order_ids=[entry_order.order_id],
                algo_ids=[stop_order.algo_id, tp_order.algo_id]
            )

            with self._lock:
                self.active_trades[trade_id] = trade
                self.total_trades += 1

            # Send notification
            self._notify("send_trade_entry",
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy="ML Day Trading",
                setup_type=f"Signal: {side}",
                leverage=self.config.leverage,
                additional_info={
                    "Confidence": f"{prediction.confidence:.1%}",
                    "Long Prob": f"{prediction.probabilities['long']:.1%}",
                    "Short Prob": f"{prediction.probabilities['short']:.1%}",
                    "R:R": f"1:{self.config.take_profit_pct/self.config.stop_loss_pct:.1f}"
                }
            )

            logger.info(f"Trade executed: {trade_id} - {side} {symbol} @ {entry_price:.2f}")

            return trade

        except BinanceFuturesError as e:
            logger.error(f"Trade execution failed: {e}")
            self._notify("send_error",
                error_message=str(e),
                context="Trade Execution",
                symbol=symbol
            )
            return None

    def check_positions(self):
        """Check status of active trades."""
        with self._lock:
            trades_to_remove = []

            for trade_id, trade in self.active_trades.items():
                try:
                    positions = self.client.get_positions(trade.symbol)

                    position_open = False
                    for pos in positions:
                        pos_amt = float(pos.get("positionAmt", 0))
                        if abs(pos_amt) > 0:
                            position_open = True
                            break

                    if not position_open:
                        self._handle_trade_close(trade)
                        trades_to_remove.append(trade_id)

                except BinanceFuturesError as e:
                    logger.error(f"Failed to check position for {trade.symbol}: {e}")

            for trade_id in trades_to_remove:
                del self.active_trades[trade_id]

    def _handle_trade_close(self, trade: ActiveTrade):
        """Handle trade closure."""
        trade.status = "CLOSED"
        trade.exit_time = datetime.now()

        try:
            trades = self.client.get_account_trades(trade.symbol, limit=10)
            if trades:
                latest = trades[-1]
                trade.exit_price = float(latest.get("price", 0))

                # Determine exit reason
                if trade.side == "LONG":
                    if trade.exit_price <= trade.stop_loss * 1.01:
                        trade.exit_reason = "Stop Loss"
                    elif trade.exit_price >= trade.take_profit * 0.99:
                        trade.exit_reason = "Take Profit"
                        self.winning_trades += 1
                    else:
                        trade.exit_reason = "Manual/Other"
                else:
                    if trade.exit_price >= trade.stop_loss * 0.99:
                        trade.exit_reason = "Stop Loss"
                    elif trade.exit_price <= trade.take_profit * 1.01:
                        trade.exit_reason = "Take Profit"
                        self.winning_trades += 1
                    else:
                        trade.exit_reason = "Manual/Other"

                # Calculate PnL
                if trade.side == "LONG":
                    trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
                else:
                    trade.pnl = (trade.entry_price - trade.exit_price) * trade.quantity

                self.daily_pnl += trade.pnl

                pnl_pct = (trade.pnl / (trade.entry_price * trade.quantity)) * 100
                duration = trade.exit_time - trade.entry_time

                # Store in history
                self.trade_history.append({
                    'trade_id': trade.trade_id,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'pnl': trade.pnl,
                    'pnl_pct': pnl_pct,
                    'confidence': trade.confidence,
                    'exit_reason': trade.exit_reason,
                    'duration': str(duration)
                })

                # Send notification
                self._notify("send_trade_exit",
                    symbol=trade.symbol,
                    side=trade.side,
                    quantity=trade.quantity,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    pnl=trade.pnl,
                    pnl_percent=pnl_pct,
                    exit_reason=trade.exit_reason,
                    strategy="ML Day Trading",
                    duration=str(duration).split('.')[0],
                    additional_info={
                        "Confidence": f"{trade.confidence:.1%}",
                        "Win Rate": f"{self.winning_trades}/{self.total_trades}"
                    }
                )

                logger.info(f"Trade closed: {trade.trade_id} - PnL: ${trade.pnl:.2f}")

        except BinanceFuturesError as e:
            logger.error(f"Failed to get exit details: {e}")

    def close_all_positions(self, reason: str = "Manual"):
        """Close all open positions."""
        with self._lock:
            for trade_id, trade in list(self.active_trades.items()):
                try:
                    # Cancel algo orders
                    for algo_id in trade.algo_ids:
                        try:
                            self.client.cancel_algo_order(trade.symbol, algo_id)
                        except BinanceFuturesError:
                            pass

                    # Close position
                    close_side = OrderSide.SELL if trade.side == "LONG" else OrderSide.BUY
                    self.client.market_order(
                        symbol=trade.symbol,
                        side=close_side,
                        quantity=trade.quantity
                    )

                    trade.exit_reason = reason
                    self._handle_trade_close(trade)

                except BinanceFuturesError as e:
                    logger.error(f"Failed to close {trade_id}: {e}")

            self.active_trades.clear()

    def _should_retrain(self) -> bool:
        """Check if model should be retrained."""
        if self.model_trained_at is None:
            return True

        hours_since_train = (datetime.now() - self.model_trained_at).total_seconds() / 3600
        return hours_since_train >= self.config.model_retrain_hours

    def run(self, symbols: List[str] = None, auto_trade: bool = True):
        """
        Run the trading bot.

        Args:
            symbols: List of symbols to trade
            auto_trade: Automatically execute trades (default: True)
        """
        symbols = symbols or self.config.symbols
        self._running = True

        logger.info(f"Starting ML Trading Bot for {symbols}")

        # Initial model training
        if not self.model.is_trained:
            try:
                self.train_model(symbols)
            except Exception as e:
                logger.error(f"Initial training failed: {e}")
                return

        self._notify("send_custom",
            title="BOT STARTED",
            body=f"<b>Symbols:</b> {', '.join(symbols)}\n"
                 f"<b>Timeframe:</b> {self.config.timeframe}\n"
                 f"<b>Auto-trade:</b> {'Enabled' if auto_trade else 'Disabled'}\n"
                 f"<b>Risk/trade:</b> {self.config.risk_per_trade_pct}%\n"
                 f"<b>Leverage:</b> {self.config.leverage}x",
            emoji="🤖"
        )

        last_scan_time = 0

        while self._running:
            try:
                current_time = time.time()

                # Check if should retrain
                if self._should_retrain():
                    logger.info("Retraining model...")
                    self.train_model(symbols)

                # Check active positions
                self.check_positions()

                # Scan interval check
                if current_time - last_scan_time < self.config.scan_interval_seconds:
                    time.sleep(1)
                    continue

                last_scan_time = current_time

                # Check trading hours
                if not self._is_trading_hours():
                    logger.debug("Outside trading hours")
                    continue

                # Count open positions
                open_positions = len(self.active_trades)
                positions_by_symbol = {}
                for trade in self.active_trades.values():
                    positions_by_symbol[trade.symbol] = positions_by_symbol.get(trade.symbol, 0) + 1

                # Scan symbols
                scan_results = []
                for symbol in symbols:
                    # Check position limits
                    if open_positions >= self.config.max_positions:
                        break

                    if positions_by_symbol.get(symbol, 0) >= self.config.max_position_per_symbol:
                        continue

                    # Scan for signal
                    prediction = self.scan_symbol(symbol)

                    if prediction is None:
                        scan_results.append(f"{symbol}:ERR")
                        continue

                    # Log scan result
                    signal_str = "L" if prediction.signal == 1 else "S" if prediction.signal == -1 else "-"
                    scan_results.append(f"{symbol}:{signal_str}({prediction.confidence:.0%})")

                    if prediction.signal == 0:
                        continue

                    if prediction.confidence < self.config.min_confidence:
                        continue

                    logger.info(
                        f"Signal: {symbol} - "
                        f"{'LONG' if prediction.signal == 1 else 'SHORT'} "
                        f"(confidence: {prediction.confidence:.1%})"
                    )

                    # Send signal notification
                    self._notify("send_signal_alert",
                        symbol=symbol,
                        signal_type="ML Prediction",
                        direction="LONG" if prediction.signal == 1 else "SHORT",
                        price=self.symbol_data.get(symbol, {}).get('current_price', 0),
                        strategy="ML Day Trading",
                        setup_details={
                            "Confidence": f"{prediction.confidence:.1%}",
                            "Long": f"{prediction.probabilities['long']:.1%}",
                            "Short": f"{prediction.probabilities['short']:.1%}",
                            "Neutral": f"{prediction.probabilities['neutral']:.1%}"
                        },
                        action_required=not auto_trade
                    )

                    if auto_trade:
                        trade = self.execute_trade(symbol, prediction)
                        if trade:
                            open_positions += 1
                            positions_by_symbol[symbol] = positions_by_symbol.get(symbol, 0) + 1

                # Log scan summary
                logger.info(f"Scan complete: {' | '.join(scan_results)} | Positions: {open_positions}/{self.config.max_positions}")

            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                self._running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self._notify("send_error",
                    error_message=str(e),
                    context="Main Loop"
                )
                time.sleep(60)

        # Cleanup
        self._notify("send_custom",
            title="BOT STOPPED",
            body=f"<b>Total Trades:</b> {self.total_trades}\n"
                 f"<b>Win Rate:</b> {self.winning_trades}/{self.total_trades}\n"
                 f"<b>Daily PnL:</b> ${self.daily_pnl:.2f}",
            emoji="🛑"
        )

    def stop(self):
        """Stop the bot gracefully."""
        self._running = False
        if self.notifier:
            self.notifier.stop()

    def get_stats(self) -> Dict[str, Any]:
        """Get current bot statistics."""
        win_rate = self.winning_trades / max(self.total_trades, 1)

        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'daily_pnl': self.daily_pnl,
            'active_positions': len(self.active_trades),
            'model_trained_at': self.model_trained_at.isoformat() if self.model_trained_at else None,
            'last_predictions': {
                s: {
                    'signal': p.signal,
                    'confidence': p.confidence,
                    'probabilities': p.probabilities
                }
                for s, p in self.last_predictions.items()
            }
        }


# Example usage
if __name__ == "__main__":
    import os

    API_KEY = os.getenv("BINANCE_API_KEY", "your_api_key")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "your_api_secret")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "your_chat_id")

    # Initialize clients
    binance_client = BinanceFuturesClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=True
    )

    telegram_notifier = TelegramNotifier(
        bot_token=TELEGRAM_TOKEN,
        chat_id=TELEGRAM_CHAT_ID
    )

    # Configure bot
    config = BotConfig(
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        timeframe="15m",
        risk_per_trade_pct=1.0,
        max_positions=3,
        leverage=10,
        stop_loss_pct=1.5,
        take_profit_pct=3.0,
        use_atr_stops=True,
        scan_interval_seconds=60
    )

    # Create and run bot
    bot = MLTradingBot(
        binance_client=binance_client,
        telegram_notifier=telegram_notifier,
        config=config
    )

    bot.run(auto_trade=True)
