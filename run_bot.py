#!/usr/bin/env python3
"""
Trading Bot Runner

Run either the ML-based day trading strategy or the Trendline swing trading strategy.

Usage:
    # Run ML strategy (default) with auto-trading
    python run_bot.py --symbols BTCUSDT ETHUSDT SOLUSDT

    # Run with specific symbols
    python run_bot.py --symbols BTCUSDT ETHUSDT --auto-trade

    # Run trendline strategy
    python run_bot.py --strategy trendline --symbols BTCUSDT

    # Train model only
    python run_bot.py --train-only --symbols BTCUSDT ETHUSDT

    # Dry run (scan without trading)
    python run_bot.py --dry-run --symbols BTCUSDT
"""

import argparse
import logging
import sys
import os
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
except ImportError:
    pass

from binance_futures import BinanceFuturesClient, BinanceFuturesError
from telegram_notifier import TelegramNotifier


def setup_logging(verbose: bool = False, log_file: str = "trading_bot.log"):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file)
        ]
    )


def get_all_symbols(client: BinanceFuturesClient, quote_asset: str = "USDT") -> list:
    """Get all available trading symbols."""
    try:
        info = client.get_exchange_info()
        symbols = []
        for s in info.get('symbols', []):
            if (s.get('quoteAsset') == quote_asset and
                s.get('status') == 'TRADING' and
                s.get('contractType') == 'PERPETUAL'):
                symbols.append(s['symbol'])
        return sorted(symbols)
    except BinanceFuturesError as e:
        logging.error(f"Failed to get symbols: {e}")
        return []


def create_binance_client(testnet: bool = True) -> BinanceFuturesClient:
    """Create Binance client from environment."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET required")

    return BinanceFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        recv_window=int(os.getenv("BINANCE_RECV_WINDOW", "5000"))
    )


def create_telegram_notifier() -> TelegramNotifier | None:
    """Create Telegram notifier if configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logging.warning("Telegram not configured")
        return None

    notifier = TelegramNotifier(
        bot_token=token,
        chat_id=chat_id,
        rate_limit=float(os.getenv("TELEGRAM_RATE_LIMIT", "1.0")),
        async_mode=os.getenv("TELEGRAM_ASYNC", "true").lower() == "true"
    )

    if notifier.test_connection():
        logging.info("Telegram connected")
    else:
        logging.warning("Telegram connection failed")

    return notifier


def run_ml_strategy(args, client, notifier):
    """Run ML-based trading strategy."""
    from ml_strategy import MLTradingBot, BotConfig

    config = BotConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "1.0")),
        max_positions=int(os.getenv("MAX_POSITIONS", "3")),
        leverage=int(os.getenv("LEVERAGE", "10")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "1.5")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "3.0")),
        use_atr_stops=os.getenv("USE_ATR_STOPS", "true").lower() == "true",
        scan_interval_seconds=int(os.getenv("SCAN_INTERVAL", "60")),
        signal_threshold=float(os.getenv("SIGNAL_THRESHOLD", "0.6")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.55"))
    )

    bot = MLTradingBot(
        binance_client=client,
        telegram_notifier=notifier,
        config=config
    )

    if args.train_only:
        logging.info("Training model only...")
        metrics = bot.train_model(args.symbols)
        print("\nTraining Results:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
        return

    if args.dry_run:
        logging.info("Dry run - scanning for signals...")
        if not bot.model.is_trained:
            bot.train_model(args.symbols)

        for symbol in args.symbols:
            prediction = bot.scan_symbol(symbol)
            if prediction:
                signal = "LONG" if prediction.signal == 1 else "SHORT" if prediction.signal == -1 else "NEUTRAL"
                print(f"\n{symbol}:")
                print(f"  Signal: {signal}")
                print(f"  Confidence: {prediction.confidence:.1%}")
                print(f"  Probabilities: L={prediction.probabilities['long']:.1%}, "
                      f"S={prediction.probabilities['short']:.1%}, "
                      f"N={prediction.probabilities['neutral']:.1%}")
        return

    # Run with auto-trading
    bot.run(symbols=args.symbols, auto_trade=args.auto_trade)


def run_trendline_strategy(args, client, notifier):
    """Run trendline swing trading strategy."""
    from trendline_strategy import TrendlineStrategyBot

    config = {
        "timeframe": args.timeframe,
        "risk_per_trade_pct": float(os.getenv("RISK_PER_TRADE_PCT", "1.0")),
        "max_positions": int(os.getenv("MAX_POSITIONS", "3")),
        "leverage": int(os.getenv("LEVERAGE", "10")),
        "enable_bounce_setups": True,
        "enable_break_2pt_setups": True,
        "enable_break_3pt_setups": True,
        "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.6")),
        "enable_trailing_stop": True,
        "take_profit_rr_ratio": float(os.getenv("TAKE_PROFIT_RR", "2.0")),
    }

    bot = TrendlineStrategyBot(
        binance_client=client,
        telegram_notifier=notifier,
        config=config
    )

    if args.dry_run:
        logging.info("Dry run - scanning for setups...")
        for symbol in args.symbols:
            setups = bot.scan_for_setups(symbol)
            if setups:
                for setup in setups:
                    print(f"\n{symbol}: {setup.setup_type.value}")
                    print(f"  Direction: {setup.direction}")
                    print(f"  Entry: ${setup.entry_price:,.2f}")
                    print(f"  Stop Loss: ${setup.stop_loss_price:,.2f}")
                    print(f"  Confidence: {setup.confidence:.0%}")
            else:
                print(f"\n{symbol}: No setups found")
        return

    bot.run(symbols=args.symbols, auto_trade=args.auto_trade)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trading Bot - ML or Trendline Strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--strategy",
        choices=["ml", "trendline"],
        default="ml",
        help="Strategy to use (default: ml)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT"],
        help="Symbols to trade"
    )
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="Trade all available USDT perpetual symbols"
    )
    parser.add_argument(
        "--top-symbols",
        type=int,
        metavar="N",
        help="Trade top N symbols by volume"
    )
    parser.add_argument(
        "--timeframe",
        default="15m",
        help="Trading timeframe (default: 15m for ML, 4h for trendline)"
    )
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        default=True,
        help="Enable automatic trading (default: True)"
    )
    parser.add_argument(
        "--signal-only",
        action="store_true",
        help="Signal-only mode, no auto trading"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan for signals without trading"
    )
    parser.add_argument(
        "--train-only",
        action="store_true",
        help="Train ML model only (no trading)"
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        default=True,
        help="Use testnet (default: True)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live/production mode (overrides --testnet)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    # Setup
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Handle auto-trade flag
    if args.signal_only:
        args.auto_trade = False

    # Determine testnet mode
    testnet = not args.live

    try:
        # Create clients
        logger.info("Initializing Binance client...")
        client = create_binance_client(testnet=testnet)

        # Verify connection
        try:
            account = client.get_account()
            balance = float(account.get("totalWalletBalance", 0))
            logger.info(f"Connected - Balance: ${balance:,.2f}")
        except BinanceFuturesError as e:
            logger.error(f"Failed to connect: {e}")
            return

        # Get symbols
        if args.all_symbols:
            args.symbols = get_all_symbols(client)
            logger.info(f"Trading all {len(args.symbols)} symbols")
        elif args.top_symbols:
            all_syms = get_all_symbols(client)
            # Get top by 24h volume
            volumes = []
            for sym in all_syms[:50]:  # Check top 50
                try:
                    ticker = client.get_ticker_24hr(sym)
                    vol = float(ticker.get('quoteVolume', 0))
                    volumes.append((sym, vol))
                except:
                    pass
            volumes.sort(key=lambda x: x[1], reverse=True)
            args.symbols = [s[0] for s in volumes[:args.top_symbols]]
            logger.info(f"Trading top {len(args.symbols)} symbols: {args.symbols}")

        # Set default timeframe based on strategy
        if args.strategy == "trendline" and args.timeframe == "15m":
            args.timeframe = "4h"

        logger.info(f"Mode: {'TESTNET' if testnet else 'PRODUCTION'}")
        logger.info(f"Strategy: {args.strategy.upper()}")
        logger.info(f"Symbols: {', '.join(args.symbols)}")
        logger.info(f"Timeframe: {args.timeframe}")
        logger.info(f"Auto-trade: {args.auto_trade}")

        # Safety warning for production
        if not testnet and args.auto_trade:
            logger.warning("=" * 50)
            logger.warning("PRODUCTION MODE WITH AUTO-TRADING!")
            logger.warning("Real money at risk!")
            logger.warning("=" * 50)
            response = input("Type 'CONFIRM' to proceed: ")
            if response != "CONFIRM":
                logger.info("Aborted")
                return

        # Create Telegram notifier
        logger.info("Initializing Telegram...")
        notifier = create_telegram_notifier()

        # Run strategy
        if args.strategy == "ml":
            run_ml_strategy(args, client, notifier)
        else:
            run_trendline_strategy(args, client, notifier)

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
