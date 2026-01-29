#!/usr/bin/env python3
"""
Trendline Strategy Trading Bot Runner

Simple entry point to run the Trendline Strategy bot with configuration
from environment variables or .env file.

Usage:
    # With environment variables
    export BINANCE_API_KEY=your_key
    export BINANCE_API_SECRET=your_secret
    export TELEGRAM_BOT_TOKEN=your_token
    export TELEGRAM_CHAT_ID=your_chat_id
    python run_bot.py

    # Or create a .env file with the same variables
    python run_bot.py

    # Run with specific symbols
    python run_bot.py --symbols BTCUSDT ETHUSDT SOLUSDT

    # Enable auto-trading (be careful!)
    python run_bot.py --auto-trade

    # Run in signal-only mode (default)
    python run_bot.py --signal-only
"""

import argparse
import logging
import sys
from pathlib import Path

# Try to load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
except ImportError:
    pass

from config import load_config, BotConfig
from binance_futures import BinanceFuturesClient
from telegram_notifier import TelegramNotifier
from trendline_strategy import TrendlineStrategyBot


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('trendline_bot.log')
        ]
    )


def create_binance_client(config: BotConfig) -> BinanceFuturesClient:
    """Create and configure Binance client."""
    return BinanceFuturesClient(
        api_key=config.binance.api_key,
        api_secret=config.binance.api_secret,
        testnet=config.binance.testnet,
        recv_window=config.binance.recv_window
    )


def create_telegram_notifier(config: BotConfig) -> TelegramNotifier | None:
    """Create Telegram notifier if enabled."""
    if not config.telegram.enabled:
        return None

    if not config.telegram.bot_token or not config.telegram.chat_id:
        logging.warning("Telegram not configured, notifications disabled")
        return None

    notifier = TelegramNotifier(
        bot_token=config.telegram.bot_token,
        chat_id=config.telegram.chat_id,
        rate_limit=config.telegram.rate_limit,
        async_mode=config.telegram.async_mode
    )

    # Test connection
    if notifier.test_connection():
        logging.info("Telegram connection successful")
    else:
        logging.warning("Telegram connection failed")

    return notifier


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Trendline Strategy Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Symbols to trade (default: from config)"
    )
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="Enable automatic trading (default: signal-only)"
    )
    parser.add_argument(
        "--signal-only",
        action="store_true",
        default=True,
        help="Run in signal-only mode (default)"
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Force testnet mode"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - scan for setups without trading"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()

        # Override from command line
        if args.testnet:
            config.binance.testnet = True

        if args.symbols:
            config.symbols = args.symbols

        auto_trade = args.auto_trade and not args.signal_only and not args.dry_run

        # Log configuration
        logger.info(f"Mode: {'TESTNET' if config.binance.testnet else 'PRODUCTION'}")
        logger.info(f"Symbols: {', '.join(config.symbols)}")
        logger.info(f"Auto-trade: {auto_trade}")
        logger.info(f"Timeframe: {config.trading.timeframe}")
        logger.info(f"Risk per trade: {config.risk.risk_per_trade_pct}%")
        logger.info(f"Leverage: {config.risk.leverage}x")

        # Safety warning for production
        if not config.binance.testnet and auto_trade:
            logger.warning("=" * 50)
            logger.warning("PRODUCTION MODE WITH AUTO-TRADING ENABLED!")
            logger.warning("Real money will be at risk!")
            logger.warning("=" * 50)
            response = input("Type 'CONFIRM' to proceed: ")
            if response != "CONFIRM":
                logger.info("Aborted by user")
                return

        # Create clients
        logger.info("Initializing Binance client...")
        binance_client = create_binance_client(config)

        # Verify connection
        try:
            account = binance_client.get_account()
            balance = float(account.get("totalWalletBalance", 0))
            logger.info(f"Account balance: ${balance:,.2f}")
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            return

        logger.info("Initializing Telegram notifier...")
        telegram_notifier = create_telegram_notifier(config)

        # Create bot
        logger.info("Creating trading bot...")
        bot = TrendlineStrategyBot(
            binance_client=binance_client,
            telegram_notifier=telegram_notifier,
            config=config.to_strategy_config()
        )

        # Run bot
        if args.dry_run:
            logger.info("Starting dry run - scanning for setups...")
            for symbol in config.symbols:
                setups = bot.scan_for_setups(symbol)
                if setups:
                    for setup in setups:
                        logger.info(
                            f"Found setup: {setup.setup_type.value} "
                            f"{setup.direction} {symbol} @ {setup.entry_price:.2f} "
                            f"(confidence: {setup.confidence:.0%})"
                        )
                else:
                    logger.info(f"No setups found for {symbol}")
        else:
            logger.info("Starting trading bot...")
            bot.run(
                symbols=config.symbols,
                auto_trade=auto_trade
            )

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
