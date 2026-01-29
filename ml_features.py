"""
ML Feature Engineering Module

Extracts technical indicators and features from OHLCV data for ML model training.
Uses proven indicators that have shown effectiveness in quantitative trading.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FeatureSet:
    """Container for extracted features."""
    features: np.ndarray
    feature_names: List[str]
    timestamps: np.ndarray
    prices: np.ndarray


class FeatureEngineer:
    """
    Technical indicator and feature extraction for ML trading models.

    Implements well-established indicators used by professional quants:
    - Trend: SMA, EMA, MACD, ADX
    - Momentum: RSI, Stochastic, CCI, Williams %R, ROC
    - Volatility: Bollinger Bands, ATR, Keltner Channels
    - Volume: OBV, VWAP, MFI, Volume SMA
    - Price Action: Candlestick patterns, Support/Resistance
    """

    def __init__(self):
        self.feature_names = []

    # ==================== TREND INDICATORS ====================

    def sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average."""
        result = np.full(len(data), np.nan)
        for i in range(period - 1, len(data)):
            result[i] = np.mean(data[i - period + 1:i + 1])
        return result

    def ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average."""
        result = np.full(len(data), np.nan)
        multiplier = 2 / (period + 1)

        # Start with SMA
        result[period - 1] = np.mean(data[:period])

        for i in range(period, len(data)):
            result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]

        return result

    def macd(
        self,
        close: np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD - Moving Average Convergence Divergence."""
        ema_fast = self.ema(close, fast)
        ema_slow = self.ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def adx(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Average Directional Index - measures trend strength."""
        n = len(close)

        # True Range
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )

        # Directional Movement
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        for i in range(1, n):
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]

            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move

        # Smoothed values
        atr = self.ema(tr, period)
        plus_di = 100 * self.ema(plus_dm, period) / np.where(atr == 0, 1, atr)
        minus_di = 100 * self.ema(minus_dm, period) / np.where(atr == 0, 1, atr)

        # ADX
        dx = 100 * np.abs(plus_di - minus_di) / np.where(plus_di + minus_di == 0, 1, plus_di + minus_di)
        adx = self.ema(dx, period)

        return adx, plus_di, minus_di

    # ==================== MOMENTUM INDICATORS ====================

    def rsi(self, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index."""
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.zeros(len(close))
        avg_loss = np.zeros(len(close))

        # First average
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])

        # Subsequent averages (smoothed)
        for i in range(period + 1, len(close)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

        rs = np.where(avg_loss == 0, 100, avg_gain / avg_loss)
        rsi = 100 - (100 / (1 + rs))
        rsi[:period] = np.nan

        return rsi

    def stochastic(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        k_period: int = 14,
        d_period: int = 3
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Stochastic Oscillator."""
        n = len(close)
        k = np.full(n, np.nan)

        for i in range(k_period - 1, n):
            highest = np.max(high[i - k_period + 1:i + 1])
            lowest = np.min(low[i - k_period + 1:i + 1])
            if highest != lowest:
                k[i] = 100 * (close[i] - lowest) / (highest - lowest)
            else:
                k[i] = 50

        d = self.sma(k, d_period)
        return k, d

    def cci(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 20
    ) -> np.ndarray:
        """Commodity Channel Index."""
        tp = (high + low + close) / 3
        sma_tp = self.sma(tp, period)

        # Mean deviation
        mad = np.full(len(tp), np.nan)
        for i in range(period - 1, len(tp)):
            mad[i] = np.mean(np.abs(tp[i - period + 1:i + 1] - sma_tp[i]))

        cci = (tp - sma_tp) / (0.015 * np.where(mad == 0, 1, mad))
        return cci

    def williams_r(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> np.ndarray:
        """Williams %R."""
        n = len(close)
        wr = np.full(n, np.nan)

        for i in range(period - 1, n):
            highest = np.max(high[i - period + 1:i + 1])
            lowest = np.min(low[i - period + 1:i + 1])
            if highest != lowest:
                wr[i] = -100 * (highest - close[i]) / (highest - lowest)
            else:
                wr[i] = -50

        return wr

    def roc(self, close: np.ndarray, period: int = 10) -> np.ndarray:
        """Rate of Change."""
        roc = np.full(len(close), np.nan)
        for i in range(period, len(close)):
            if close[i - period] != 0:
                roc[i] = 100 * (close[i] - close[i - period]) / close[i - period]
        return roc

    def momentum(self, close: np.ndarray, period: int = 10) -> np.ndarray:
        """Price Momentum."""
        mom = np.full(len(close), np.nan)
        for i in range(period, len(close)):
            mom[i] = close[i] - close[i - period]
        return mom

    # ==================== VOLATILITY INDICATORS ====================

    def bollinger_bands(
        self,
        close: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Bollinger Bands."""
        middle = self.sma(close, period)

        std = np.full(len(close), np.nan)
        for i in range(period - 1, len(close)):
            std[i] = np.std(close[i - period + 1:i + 1])

        upper = middle + std_dev * std
        lower = middle - std_dev * std

        # %B - position within bands
        bandwidth = (close - lower) / np.where(upper - lower == 0, 1, upper - lower)

        return upper, middle, lower, bandwidth

    def atr(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> np.ndarray:
        """Average True Range."""
        n = len(close)
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]

        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )

        return self.ema(tr, period)

    def keltner_channels(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Keltner Channels."""
        middle = self.ema(close, ema_period)
        atr_val = self.atr(high, low, close, atr_period)

        upper = middle + multiplier * atr_val
        lower = middle - multiplier * atr_val

        return upper, middle, lower

    def volatility(self, close: np.ndarray, period: int = 20) -> np.ndarray:
        """Historical volatility (standard deviation of returns)."""
        returns = np.zeros(len(close))
        returns[1:] = np.diff(close) / close[:-1]

        vol = np.full(len(close), np.nan)
        for i in range(period, len(close)):
            vol[i] = np.std(returns[i - period + 1:i + 1]) * np.sqrt(252)  # Annualized

        return vol

    # ==================== VOLUME INDICATORS ====================

    def obv(self, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """On-Balance Volume."""
        obv = np.zeros(len(close))
        obv[0] = volume[0]

        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]

        return obv

    def vwap(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray
    ) -> np.ndarray:
        """Volume Weighted Average Price (cumulative)."""
        typical_price = (high + low + close) / 3
        cum_tp_vol = np.cumsum(typical_price * volume)
        cum_vol = np.cumsum(volume)

        return cum_tp_vol / np.where(cum_vol == 0, 1, cum_vol)

    def mfi(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        period: int = 14
    ) -> np.ndarray:
        """Money Flow Index - volume-weighted RSI."""
        tp = (high + low + close) / 3
        raw_mf = tp * volume

        pos_mf = np.zeros(len(close))
        neg_mf = np.zeros(len(close))

        for i in range(1, len(close)):
            if tp[i] > tp[i - 1]:
                pos_mf[i] = raw_mf[i]
            elif tp[i] < tp[i - 1]:
                neg_mf[i] = raw_mf[i]

        mfi = np.full(len(close), np.nan)
        for i in range(period, len(close)):
            pos_sum = np.sum(pos_mf[i - period + 1:i + 1])
            neg_sum = np.sum(neg_mf[i - period + 1:i + 1])

            if neg_sum == 0:
                mfi[i] = 100
            else:
                mfi[i] = 100 - (100 / (1 + pos_sum / neg_sum))

        return mfi

    def volume_sma_ratio(
        self,
        volume: np.ndarray,
        period: int = 20
    ) -> np.ndarray:
        """Current volume relative to SMA."""
        vol_sma = self.sma(volume, period)
        return volume / np.where(vol_sma == 0, 1, vol_sma)

    # ==================== PRICE ACTION FEATURES ====================

    def candle_features(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Extract candlestick pattern features."""
        body = close - open_
        body_size = np.abs(body)
        candle_range = high - low

        # Upper and lower shadows
        upper_shadow = np.where(
            close >= open_,
            high - close,
            high - open_
        )
        lower_shadow = np.where(
            close >= open_,
            open_ - low,
            close - low
        )

        # Body to range ratio
        body_ratio = body_size / np.where(candle_range == 0, 1, candle_range)

        # Doji detection (small body)
        doji = (body_ratio < 0.1).astype(float)

        # Hammer/Shooting star (long lower/upper shadow)
        hammer = ((lower_shadow > 2 * body_size) & (upper_shadow < body_size * 0.5)).astype(float)
        shooting_star = ((upper_shadow > 2 * body_size) & (lower_shadow < body_size * 0.5)).astype(float)

        # Engulfing patterns
        bullish_engulf = np.zeros(len(close))
        bearish_engulf = np.zeros(len(close))
        for i in range(1, len(close)):
            if body[i] > 0 and body[i - 1] < 0:  # Current bullish, previous bearish
                if open_[i] <= close[i - 1] and close[i] >= open_[i - 1]:
                    bullish_engulf[i] = 1
            if body[i] < 0 and body[i - 1] > 0:  # Current bearish, previous bullish
                if open_[i] >= close[i - 1] and close[i] <= open_[i - 1]:
                    bearish_engulf[i] = 1

        return {
            "body": body,
            "body_size": body_size,
            "body_ratio": body_ratio,
            "upper_shadow": upper_shadow,
            "lower_shadow": lower_shadow,
            "doji": doji,
            "hammer": hammer,
            "shooting_star": shooting_star,
            "bullish_engulf": bullish_engulf,
            "bearish_engulf": bearish_engulf
        }

    def support_resistance_distance(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        lookback: int = 50
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Distance to nearest support and resistance levels."""
        n = len(close)
        dist_support = np.full(n, np.nan)
        dist_resistance = np.full(n, np.nan)

        for i in range(lookback, n):
            recent_high = np.max(high[i - lookback:i])
            recent_low = np.min(low[i - lookback:i])

            dist_resistance[i] = (recent_high - close[i]) / close[i]
            dist_support[i] = (close[i] - recent_low) / close[i]

        return dist_support, dist_resistance

    # ==================== RETURNS & LABELS ====================

    def returns(self, close: np.ndarray, periods: List[int] = None) -> Dict[str, np.ndarray]:
        """Calculate returns over various periods."""
        if periods is None:
            periods = [1, 5, 10, 20]

        returns_dict = {}
        for p in periods:
            ret = np.full(len(close), np.nan)
            for i in range(p, len(close)):
                ret[i] = (close[i] - close[i - p]) / close[i - p]
            returns_dict[f"return_{p}"] = ret

        return returns_dict

    def future_returns(
        self,
        close: np.ndarray,
        periods: List[int] = None
    ) -> Dict[str, np.ndarray]:
        """Calculate future returns (for labeling)."""
        if periods is None:
            periods = [1, 5, 10]

        returns_dict = {}
        for p in periods:
            ret = np.full(len(close), np.nan)
            for i in range(len(close) - p):
                ret[i] = (close[i + p] - close[i]) / close[i]
            returns_dict[f"future_return_{p}"] = ret

        return returns_dict

    def create_labels(
        self,
        close: np.ndarray,
        forward_period: int = 5,
        threshold: float = 0.01
    ) -> np.ndarray:
        """
        Create classification labels based on future returns.

        Returns:
            1 = Long (price goes up more than threshold)
            0 = Neutral (price stays within threshold)
            -1 = Short (price goes down more than threshold)
        """
        labels = np.full(len(close), np.nan)

        for i in range(len(close) - forward_period):
            future_return = (close[i + forward_period] - close[i]) / close[i]

            if future_return > threshold:
                labels[i] = 1
            elif future_return < -threshold:
                labels[i] = -1
            else:
                labels[i] = 0

        return labels

    # ==================== MAIN FEATURE EXTRACTION ====================

    def extract_features(
        self,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        timestamps: np.ndarray = None
    ) -> FeatureSet:
        """
        Extract all features from OHLCV data.

        Args:
            open_: Open prices
            high: High prices
            low: Low prices
            close: Close prices
            volume: Volume
            timestamps: Optional timestamps

        Returns:
            FeatureSet with all extracted features
        """
        features = {}

        # Trend indicators
        features["sma_10"] = self.sma(close, 10)
        features["sma_20"] = self.sma(close, 20)
        features["sma_50"] = self.sma(close, 50)
        features["ema_10"] = self.ema(close, 10)
        features["ema_20"] = self.ema(close, 20)
        features["ema_50"] = self.ema(close, 50)

        # Price relative to MAs
        features["price_sma10_ratio"] = close / np.where(features["sma_10"] == 0, 1, features["sma_10"])
        features["price_sma20_ratio"] = close / np.where(features["sma_20"] == 0, 1, features["sma_20"])
        features["price_sma50_ratio"] = close / np.where(features["sma_50"] == 0, 1, features["sma_50"])
        features["sma10_sma20_ratio"] = features["sma_10"] / np.where(features["sma_20"] == 0, 1, features["sma_20"])
        features["sma20_sma50_ratio"] = features["sma_20"] / np.where(features["sma_50"] == 0, 1, features["sma_50"])

        # MACD
        macd_line, signal_line, histogram = self.macd(close)
        features["macd"] = macd_line
        features["macd_signal"] = signal_line
        features["macd_hist"] = histogram

        # ADX
        adx, plus_di, minus_di = self.adx(high, low, close)
        features["adx"] = adx
        features["plus_di"] = plus_di
        features["minus_di"] = minus_di
        features["di_diff"] = plus_di - minus_di

        # Momentum indicators
        features["rsi_14"] = self.rsi(close, 14)
        features["rsi_7"] = self.rsi(close, 7)

        stoch_k, stoch_d = self.stochastic(high, low, close)
        features["stoch_k"] = stoch_k
        features["stoch_d"] = stoch_d

        features["cci"] = self.cci(high, low, close)
        features["williams_r"] = self.williams_r(high, low, close)
        features["roc_10"] = self.roc(close, 10)
        features["roc_5"] = self.roc(close, 5)
        features["momentum_10"] = self.momentum(close, 10)

        # Volatility indicators
        bb_upper, bb_middle, bb_lower, bb_pct = self.bollinger_bands(close)
        features["bb_upper"] = bb_upper
        features["bb_lower"] = bb_lower
        features["bb_pct"] = bb_pct
        features["bb_width"] = (bb_upper - bb_lower) / np.where(bb_middle == 0, 1, bb_middle)

        features["atr"] = self.atr(high, low, close)
        features["atr_pct"] = features["atr"] / close
        features["volatility"] = self.volatility(close)

        kc_upper, kc_middle, kc_lower = self.keltner_channels(high, low, close)
        features["kc_upper"] = kc_upper
        features["kc_lower"] = kc_lower
        features["squeeze"] = ((bb_lower > kc_lower) & (bb_upper < kc_upper)).astype(float)

        # Volume indicators
        features["obv"] = self.obv(close, volume)
        features["obv_sma"] = self.sma(features["obv"], 20)
        features["vwap"] = self.vwap(high, low, close, volume)
        features["price_vwap_ratio"] = close / np.where(features["vwap"] == 0, 1, features["vwap"])
        features["mfi"] = self.mfi(high, low, close, volume)
        features["volume_sma_ratio"] = self.volume_sma_ratio(volume)

        # Candle features
        candle_feats = self.candle_features(open_, high, low, close)
        for name, values in candle_feats.items():
            features[f"candle_{name}"] = values

        # Support/Resistance
        dist_support, dist_resistance = self.support_resistance_distance(high, low, close)
        features["dist_support"] = dist_support
        features["dist_resistance"] = dist_resistance

        # Returns
        returns_dict = self.returns(close, [1, 3, 5, 10, 20])
        features.update(returns_dict)

        # Higher timeframe context (using longer periods)
        features["sma_100"] = self.sma(close, 100)
        features["sma_200"] = self.sma(close, 200)
        features["price_sma100_ratio"] = close / np.where(features["sma_100"] == 0, 1, features["sma_100"])
        features["price_sma200_ratio"] = close / np.where(features["sma_200"] == 0, 1, features["sma_200"])

        # Convert to arrays
        feature_names = list(features.keys())
        n_samples = len(close)
        n_features = len(feature_names)

        feature_array = np.zeros((n_samples, n_features))
        for i, name in enumerate(feature_names):
            feature_array[:, i] = features[name]

        self.feature_names = feature_names

        return FeatureSet(
            features=feature_array,
            feature_names=feature_names,
            timestamps=timestamps if timestamps is not None else np.arange(n_samples),
            prices=close.copy()
        )

    def normalize_features(
        self,
        features: np.ndarray,
        method: str = "zscore"
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Normalize features for ML training.

        Args:
            features: Feature array (n_samples, n_features)
            method: 'zscore' or 'minmax'

        Returns:
            Normalized features and normalization parameters
        """
        params = {}
        normalized = np.zeros_like(features)

        for i in range(features.shape[1]):
            col = features[:, i]
            valid_mask = ~np.isnan(col)

            if method == "zscore":
                mean = np.nanmean(col)
                std = np.nanstd(col)
                std = std if std > 0 else 1
                normalized[:, i] = (col - mean) / std
                params[f"col_{i}"] = {"mean": mean, "std": std}
            else:  # minmax
                min_val = np.nanmin(col)
                max_val = np.nanmax(col)
                range_val = max_val - min_val if max_val != min_val else 1
                normalized[:, i] = (col - min_val) / range_val
                params[f"col_{i}"] = {"min": min_val, "range": range_val}

        return normalized, params

    def prepare_sequences(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sequence_length: int = 60
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequential data for LSTM/RNN models.

        Args:
            features: Feature array (n_samples, n_features)
            labels: Label array (n_samples,)
            sequence_length: Number of time steps per sequence

        Returns:
            X: (n_sequences, sequence_length, n_features)
            y: (n_sequences,)
        """
        n_samples = len(labels)
        n_features = features.shape[1]

        # Find valid indices (no NaN in features or labels)
        valid_indices = []
        for i in range(sequence_length, n_samples):
            if not np.isnan(labels[i]):
                seq = features[i - sequence_length:i]
                if not np.any(np.isnan(seq)):
                    valid_indices.append(i)

        n_valid = len(valid_indices)
        X = np.zeros((n_valid, sequence_length, n_features))
        y = np.zeros(n_valid)

        for j, i in enumerate(valid_indices):
            X[j] = features[i - sequence_length:i]
            y[j] = labels[i]

        return X, y
