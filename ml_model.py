"""
ML Model Module for Trading Strategy

Implements an ensemble of proven ML models for trading signal generation:
- XGBoost/LightGBM for tabular features
- LSTM for sequential patterns
- Ensemble combination for robust signals

Uses cross-validation and walk-forward optimization for realistic backtesting.
"""

import numpy as np
import pickle
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for ML models."""
    # XGBoost parameters
    xgb_n_estimators: int = 100
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.1
    xgb_min_child_weight: int = 1
    xgb_subsample: float = 0.8
    xgb_colsample_bytree: float = 0.8
    xgb_reg_alpha: float = 0.1
    xgb_reg_lambda: float = 1.0

    # LSTM parameters (optimized for low memory VPS)
    lstm_units: int = 32
    lstm_dropout: float = 0.2
    lstm_recurrent_dropout: float = 0.2
    lstm_dense_units: int = 16
    lstm_epochs: int = 30
    lstm_batch_size: int = 16
    lstm_sequence_length: int = 30

    # Ensemble parameters
    ensemble_weights: Dict[str, float] = field(default_factory=lambda: {
        "xgb": 0.6,
        "lstm": 0.4
    })

    # Training parameters
    train_test_split: float = 0.2
    validation_split: float = 0.1
    label_threshold: float = 0.01  # 1% move for signal
    forward_period: int = 5  # Bars to look ahead for labeling

    # Prediction parameters
    signal_threshold: float = 0.6  # Probability threshold for signal
    min_confidence: float = 0.55  # Minimum confidence to act


@dataclass
class Prediction:
    """Trading signal prediction."""
    signal: int  # 1=Long, -1=Short, 0=Neutral
    confidence: float  # 0-1 confidence score
    probabilities: Dict[str, float]  # Class probabilities
    model_predictions: Dict[str, float]  # Individual model predictions
    features_used: int
    timestamp: datetime = field(default_factory=datetime.now)


class TradingModel:
    """
    Ensemble ML model for trading signal generation.

    Combines XGBoost (gradient boosting) with LSTM (deep learning) for
    robust signal generation. Uses proven techniques from quantitative finance.
    """

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.xgb_model = None
        self.lstm_model = None
        self.scaler_params = None
        self.feature_names = None
        self.is_trained = False
        self._use_gpu = False

        # Check for available libraries
        self._check_dependencies()

    def _check_dependencies(self):
        """Check and import required libraries."""
        self._has_xgb = False
        self._has_lgb = False
        self._has_sklearn = False
        self._has_tf = False

        try:
            import xgboost as xgb
            self._has_xgb = True
            self._xgb = xgb
            logger.info("XGBoost available")
        except ImportError:
            logger.warning("XGBoost not available, will use LightGBM or sklearn")

        try:
            import lightgbm as lgb
            self._has_lgb = True
            self._lgb = lgb
            logger.info("LightGBM available")
        except ImportError:
            pass

        try:
            from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import train_test_split
            self._has_sklearn = True
            self._sklearn_gb = GradientBoostingClassifier
            self._sklearn_rf = RandomForestClassifier
            self._sklearn_scaler = StandardScaler
            self._sklearn_split = train_test_split
            logger.info("Sklearn available")
        except ImportError:
            logger.warning("Sklearn not available")

        try:
            import tensorflow as tf

            # Memory optimization for VPS - only allocate memory as needed
            gpus = tf.config.list_physical_devices('GPU')
            if gpus:
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                self._use_gpu = True
                logger.info("TensorFlow with GPU available")
            else:
                # CPU memory optimization
                tf.config.threading.set_intra_op_parallelism_threads(2)
                tf.config.threading.set_inter_op_parallelism_threads(2)
                logger.info("TensorFlow available (CPU only, memory optimized)")

            self._has_tf = True
            self._tf = tf
        except ImportError:
            logger.warning("TensorFlow not available, LSTM disabled")

    def _build_xgb_model(self):
        """Build XGBoost classifier."""
        if self._has_xgb:
            return self._xgb.XGBClassifier(
                n_estimators=self.config.xgb_n_estimators,
                max_depth=self.config.xgb_max_depth,
                learning_rate=self.config.xgb_learning_rate,
                min_child_weight=self.config.xgb_min_child_weight,
                subsample=self.config.xgb_subsample,
                colsample_bytree=self.config.xgb_colsample_bytree,
                reg_alpha=self.config.xgb_reg_alpha,
                reg_lambda=self.config.xgb_reg_lambda,
                objective='multi:softprob',
                num_class=3,
                use_label_encoder=False,
                eval_metric='mlogloss',
                tree_method='hist',
                random_state=42
            )
        elif self._has_lgb:
            return self._lgb.LGBMClassifier(
                n_estimators=self.config.xgb_n_estimators,
                max_depth=self.config.xgb_max_depth,
                learning_rate=self.config.xgb_learning_rate,
                subsample=self.config.xgb_subsample,
                colsample_bytree=self.config.xgb_colsample_bytree,
                reg_alpha=self.config.xgb_reg_alpha,
                reg_lambda=self.config.xgb_reg_lambda,
                objective='multiclass',
                num_class=3,
                random_state=42,
                verbose=-1
            )
        elif self._has_sklearn:
            return self._sklearn_gb(
                n_estimators=self.config.xgb_n_estimators,
                max_depth=self.config.xgb_max_depth,
                learning_rate=self.config.xgb_learning_rate,
                random_state=42
            )
        else:
            raise ImportError("No gradient boosting library available. Install xgboost, lightgbm, or sklearn.")

    def _build_lstm_model(self, input_shape: Tuple[int, int]):
        """Build LSTM model for sequential patterns."""
        if not self._has_tf:
            return None

        tf = self._tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
        from tensorflow.keras.optimizers import Adam

        model = Sequential([
            LSTM(
                self.config.lstm_units,
                input_shape=input_shape,
                return_sequences=True,
                dropout=self.config.lstm_dropout,
                recurrent_dropout=self.config.lstm_recurrent_dropout
            ),
            BatchNormalization(),
            LSTM(
                self.config.lstm_units // 2,
                dropout=self.config.lstm_dropout,
                recurrent_dropout=self.config.lstm_recurrent_dropout
            ),
            BatchNormalization(),
            Dense(self.config.lstm_dense_units, activation='relu'),
            Dropout(self.config.lstm_dropout),
            Dense(3, activation='softmax')  # 3 classes: short, neutral, long
        ])

        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )

        return model

    def _prepare_labels(self, labels: np.ndarray) -> np.ndarray:
        """Convert labels (-1, 0, 1) to (0, 1, 2) for classification."""
        # -1 (short) -> 0, 0 (neutral) -> 1, 1 (long) -> 2
        return (labels + 1).astype(int)

    def _reverse_labels(self, labels: np.ndarray) -> np.ndarray:
        """Convert classification labels back to signal."""
        # 0 -> -1, 1 -> 0, 2 -> 1
        return labels.astype(int) - 1

    def train(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        feature_names: Optional[List[str]] = None,
        validation_data: Optional[Tuple[np.ndarray, np.ndarray]] = None
    ) -> Dict[str, Any]:
        """
        Train the ensemble model.

        Args:
            features: Feature array (n_samples, n_features)
            labels: Labels (-1, 0, 1)
            feature_names: Optional feature names
            validation_data: Optional (X_val, y_val) tuple

        Returns:
            Training metrics
        """
        logger.info("Starting model training...")

        self.feature_names = feature_names

        # Handle NaN values - fill with column median instead of dropping rows
        X = features.copy()
        y = labels.copy()

        # Fill NaN in features with column median
        for i in range(X.shape[1]):
            col = X[:, i]
            nan_mask = np.isnan(col)
            if nan_mask.any():
                median_val = np.nanmedian(col)
                if np.isnan(median_val):
                    median_val = 0
                X[nan_mask, i] = median_val

        # Remove only samples with NaN labels (future returns we can't know)
        valid_label_mask = ~np.isnan(y)
        X = X[valid_label_mask]
        y = y[valid_label_mask]

        # Also remove any remaining NaN rows (shouldn't be many)
        valid_feature_mask = ~np.isnan(X).any(axis=1)
        X = X[valid_feature_mask]
        y = y[valid_feature_mask]

        logger.info(f"Training samples: {len(X)}, Features: {X.shape[1]}")

        if len(X) < 100:
            raise ValueError(f"Not enough training samples: {len(X)}. Need at least 100.")

        # Class distribution
        unique, counts = np.unique(y, return_counts=True)
        for u, c in zip(unique, counts):
            logger.info(f"  Class {int(u)}: {c} samples ({c/len(y)*100:.1f}%)")

        # Normalize features
        if self._has_sklearn:
            self.scaler = self._sklearn_scaler()
            X_scaled = self.scaler.fit_transform(X)
        else:
            # Manual normalization
            self.scaler_params = {
                'mean': np.mean(X, axis=0),
                'std': np.std(X, axis=0)
            }
            self.scaler_params['std'][self.scaler_params['std'] == 0] = 1
            X_scaled = (X - self.scaler_params['mean']) / self.scaler_params['std']

        # Split data
        split_idx = int(len(X_scaled) * (1 - self.config.train_test_split))
        X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        metrics = {}

        # Train XGBoost
        logger.info("Training gradient boosting model...")
        self.xgb_model = self._build_xgb_model()

        y_train_cls = self._prepare_labels(y_train)
        y_test_cls = self._prepare_labels(y_test)

        self.xgb_model.fit(
            X_train, y_train_cls,
            eval_set=[(X_test, y_test_cls)],
            verbose=False
        )

        # XGBoost accuracy
        xgb_pred = self.xgb_model.predict(X_test)
        xgb_acc = np.mean(xgb_pred == y_test_cls)
        metrics['xgb_accuracy'] = xgb_acc
        logger.info(f"XGBoost accuracy: {xgb_acc:.4f}")

        # Feature importance
        if hasattr(self.xgb_model, 'feature_importances_'):
            importance = self.xgb_model.feature_importances_
            if feature_names:
                top_features = sorted(
                    zip(feature_names, importance),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
                logger.info("Top 10 features:")
                for name, imp in top_features:
                    logger.info(f"  {name}: {imp:.4f}")

        # Train LSTM if available
        if self._has_tf:
            logger.info("Training LSTM model...")
            from ml_features import FeatureEngineer
            fe = FeatureEngineer()

            # Prepare sequences
            X_seq, y_seq = fe.prepare_sequences(
                X_scaled, y,
                sequence_length=self.config.lstm_sequence_length
            )

            # Limit sequences for memory efficiency (max 5000 samples)
            max_lstm_samples = 5000
            if len(X_seq) > max_lstm_samples:
                # Use stratified sampling - take recent data
                indices = np.linspace(0, len(X_seq) - 1, max_lstm_samples, dtype=int)
                X_seq = X_seq[indices]
                y_seq = y_seq[indices]
                logger.info(f"LSTM training limited to {max_lstm_samples} sequences for memory")

            if len(X_seq) > 100:
                y_seq_cls = self._prepare_labels(y_seq)

                # Split sequences
                seq_split = int(len(X_seq) * (1 - self.config.train_test_split))
                X_seq_train = X_seq[:seq_split]
                y_seq_train = y_seq_cls[:seq_split]
                X_seq_test = X_seq[seq_split:]
                y_seq_test = y_seq_cls[seq_split:]

                # Build and train LSTM
                self.lstm_model = self._build_lstm_model(
                    input_shape=(self.config.lstm_sequence_length, X.shape[1])
                )

                from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

                callbacks = [
                    EarlyStopping(patience=10, restore_best_weights=True),
                    ReduceLROnPlateau(factor=0.5, patience=5)
                ]

                history = self.lstm_model.fit(
                    X_seq_train, y_seq_train,
                    validation_data=(X_seq_test, y_seq_test),
                    epochs=self.config.lstm_epochs,
                    batch_size=self.config.lstm_batch_size,
                    callbacks=callbacks,
                    verbose=0
                )

                # LSTM accuracy
                lstm_pred = np.argmax(self.lstm_model.predict(X_seq_test, verbose=0), axis=1)
                lstm_acc = np.mean(lstm_pred == y_seq_test)
                metrics['lstm_accuracy'] = lstm_acc
                logger.info(f"LSTM accuracy: {lstm_acc:.4f}")
            else:
                logger.warning("Not enough data for LSTM training")
                self.lstm_model = None

        self.is_trained = True
        metrics['total_samples'] = len(X)
        metrics['train_samples'] = len(X_train)
        metrics['test_samples'] = len(X_test)

        logger.info("Model training complete")
        return metrics

    def predict(
        self,
        features: np.ndarray,
        sequence_data: Optional[np.ndarray] = None
    ) -> Prediction:
        """
        Generate trading signal prediction.

        Args:
            features: Feature vector (1, n_features) or (n_features,)
            sequence_data: Optional sequence data for LSTM (seq_len, n_features)

        Returns:
            Prediction with signal and confidence
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() first.")

        # Ensure 2D
        if features.ndim == 1:
            features = features.reshape(1, -1)

        # Handle NaN values - fill with 0 (will be normalized anyway)
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        # Normalize
        if hasattr(self, 'scaler') and self.scaler is not None:
            features_scaled = self.scaler.transform(features)
        elif self.scaler_params is not None:
            features_scaled = (features - self.scaler_params['mean']) / self.scaler_params['std']
        else:
            features_scaled = features

        # Handle any NaN from normalization
        features_scaled = np.nan_to_num(features_scaled, nan=0.0, posinf=0.0, neginf=0.0)

        model_predictions = {}
        probabilities = {'short': 0, 'neutral': 0, 'long': 0}

        # XGBoost prediction
        if self.xgb_model is not None:
            xgb_proba = self.xgb_model.predict_proba(features_scaled)[0]
            # Sanitize XGBoost output
            xgb_proba = np.nan_to_num(xgb_proba, nan=0.33, posinf=0.33, neginf=0.33)
            model_predictions['xgb'] = {
                'short': float(xgb_proba[0]),
                'neutral': float(xgb_proba[1]),
                'long': float(xgb_proba[2])
            }

        # LSTM prediction
        if self.lstm_model is not None and sequence_data is not None:
            if sequence_data.ndim == 2:
                sequence_data = sequence_data.reshape(1, *sequence_data.shape)

            # Handle NaN values in sequence data
            sequence_data = np.nan_to_num(sequence_data, nan=0.0, posinf=0.0, neginf=0.0)

            # Normalize sequence
            if hasattr(self, 'scaler') and self.scaler is not None:
                seq_scaled = np.zeros_like(sequence_data)
                for i in range(sequence_data.shape[1]):
                    seq_scaled[0, i] = self.scaler.transform(sequence_data[0, i:i+1])
            elif self.scaler_params is not None:
                seq_scaled = (sequence_data - self.scaler_params['mean']) / self.scaler_params['std']
            else:
                seq_scaled = sequence_data

            # Handle NaN after normalization
            seq_scaled = np.nan_to_num(seq_scaled, nan=0.0, posinf=0.0, neginf=0.0)

            lstm_proba = self.lstm_model.predict(seq_scaled, verbose=0)[0]
            # Sanitize LSTM output
            lstm_proba = np.nan_to_num(lstm_proba, nan=0.33, posinf=0.33, neginf=0.33)
            model_predictions['lstm'] = {
                'short': float(lstm_proba[0]),
                'neutral': float(lstm_proba[1]),
                'long': float(lstm_proba[2])
            }

        # Ensemble combination
        weights = self.config.ensemble_weights
        total_weight = 0

        for model_name, preds in model_predictions.items():
            weight = weights.get(model_name, 0.5)
            total_weight += weight
            for cls in ['short', 'neutral', 'long']:
                probabilities[cls] += preds[cls] * weight

        # Normalize
        if total_weight > 0:
            for cls in probabilities:
                probabilities[cls] /= total_weight

        # Sanitize final probabilities - ensure no NaN
        for cls in probabilities:
            if np.isnan(probabilities[cls]) or np.isinf(probabilities[cls]):
                probabilities[cls] = 0.33

        # Determine signal
        max_prob = max(probabilities.values())
        max_class = max(probabilities, key=probabilities.get)

        if max_prob >= self.config.signal_threshold:
            if max_class == 'long':
                signal = 1
            elif max_class == 'short':
                signal = -1
            else:
                signal = 0
        else:
            signal = 0

        # Confidence is the probability spread - ensure not NaN
        confidence = max_prob if not np.isnan(max_prob) else 0.33

        return Prediction(
            signal=signal,
            confidence=confidence,
            probabilities=probabilities,
            model_predictions=model_predictions,
            features_used=features.shape[1]
        )

    def predict_batch(
        self,
        features: np.ndarray,
        sequence_data: Optional[np.ndarray] = None
    ) -> List[Prediction]:
        """Generate predictions for multiple samples."""
        predictions = []
        for i in range(len(features)):
            seq = None
            if sequence_data is not None and i < len(sequence_data):
                seq = sequence_data[i]
            predictions.append(self.predict(features[i], seq))
        return predictions

    def save(self, path: str):
        """Save model to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save XGBoost
        if self.xgb_model is not None:
            if self._has_xgb:
                self.xgb_model.save_model(str(path / "xgb_model.json"))
            else:
                with open(path / "xgb_model.pkl", 'wb') as f:
                    pickle.dump(self.xgb_model, f)

        # Save LSTM
        if self.lstm_model is not None:
            self.lstm_model.save(str(path / "lstm_model.keras"))

        # Save scaler and config
        save_data = {
            'config': self.config.__dict__,
            'feature_names': self.feature_names,
            'scaler_params': self.scaler_params,
            'is_trained': self.is_trained
        }

        if hasattr(self, 'scaler') and self.scaler is not None:
            save_data['scaler_mean'] = self.scaler.mean_.tolist()
            save_data['scaler_scale'] = self.scaler.scale_.tolist()

        with open(path / "model_meta.json", 'w') as f:
            json.dump(save_data, f, indent=2, default=str)

        logger.info(f"Model saved to {path}")

    def load(self, path: str):
        """Load model from disk."""
        path = Path(path)

        # Load metadata
        with open(path / "model_meta.json", 'r') as f:
            save_data = json.load(f)

        self.config = ModelConfig(**save_data['config'])
        self.feature_names = save_data['feature_names']
        self.scaler_params = save_data.get('scaler_params')
        self.is_trained = save_data['is_trained']

        # Restore scaler
        if 'scaler_mean' in save_data and self._has_sklearn:
            self.scaler = self._sklearn_scaler()
            self.scaler.mean_ = np.array(save_data['scaler_mean'])
            self.scaler.scale_ = np.array(save_data['scaler_scale'])
            self.scaler.var_ = self.scaler.scale_ ** 2
            self.scaler.n_features_in_ = len(self.scaler.mean_)

        # Load XGBoost
        if (path / "xgb_model.json").exists():
            if self._has_xgb:
                self.xgb_model = self._xgb.XGBClassifier()
                self.xgb_model.load_model(str(path / "xgb_model.json"))
        elif (path / "xgb_model.pkl").exists():
            with open(path / "xgb_model.pkl", 'rb') as f:
                self.xgb_model = pickle.load(f)

        # Load LSTM
        if (path / "lstm_model.keras").exists() and self._has_tf:
            self.lstm_model = self._tf.keras.models.load_model(str(path / "lstm_model.keras"))

        logger.info(f"Model loaded from {path}")


class WalkForwardValidator:
    """
    Walk-forward validation for realistic backtesting.

    Implements expanding window training to avoid look-ahead bias.
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_ratio: float = 0.7,
        gap: int = 0
    ):
        self.n_splits = n_splits
        self.train_ratio = train_ratio
        self.gap = gap

    def split(
        self,
        X: np.ndarray,
        y: np.ndarray = None
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate train/test splits for walk-forward validation.

        Returns list of (train_indices, test_indices) tuples.
        """
        n_samples = len(X)
        test_size = n_samples // (self.n_splits + 1)
        splits = []

        for i in range(self.n_splits):
            train_end = int(n_samples * self.train_ratio) + i * test_size
            test_start = train_end + self.gap
            test_end = test_start + test_size

            if test_end > n_samples:
                break

            train_idx = np.arange(0, train_end)
            test_idx = np.arange(test_start, test_end)

            splits.append((train_idx, test_idx))

        return splits

    def validate(
        self,
        model: TradingModel,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Perform walk-forward validation.

        Returns metrics for each fold and overall.
        """
        splits = self.split(X, y)
        fold_metrics = []

        for fold, (train_idx, test_idx) in enumerate(splits):
            logger.info(f"Fold {fold + 1}/{len(splits)}")

            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Train on this fold
            model_copy = TradingModel(model.config)
            model_copy.train(X_train, y_train, feature_names)

            # Predict
            predictions = model_copy.predict_batch(X_test)
            pred_signals = np.array([p.signal for p in predictions])

            # Metrics
            accuracy = np.mean(pred_signals == y_test)

            # Direction accuracy (ignoring neutral)
            direction_mask = (pred_signals != 0) & (y_test != 0)
            if np.sum(direction_mask) > 0:
                direction_acc = np.mean(pred_signals[direction_mask] == y_test[direction_mask])
            else:
                direction_acc = 0

            fold_metrics.append({
                'fold': fold + 1,
                'train_size': len(train_idx),
                'test_size': len(test_idx),
                'accuracy': accuracy,
                'direction_accuracy': direction_acc
            })

            logger.info(f"  Accuracy: {accuracy:.4f}, Direction: {direction_acc:.4f}")

        # Overall metrics
        avg_accuracy = np.mean([m['accuracy'] for m in fold_metrics])
        avg_direction = np.mean([m['direction_accuracy'] for m in fold_metrics])

        return {
            'fold_metrics': fold_metrics,
            'avg_accuracy': avg_accuracy,
            'avg_direction_accuracy': avg_direction
        }
