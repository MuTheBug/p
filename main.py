#!/usr/bin/env python3
"""
Main Entry Point - Donchian Breakout Trading Bot

This is the main trading strategy that runs 24/7 and trades
BTCUSDT, ETHUSDT, and SOLUSDT using Donchian channel breakouts
with EMA trend filters and ATR-based position sizing.

Usage:
    # Using environment variables (recommended):
    export BINANCE_API_KEY="your_api_key"
    export BINANCE_API_SECRET="your_api_secret"
    export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
    export TELEGRAM_CHAT_ID="your_telegram_chat_id"
    python main.py

    # Using command line arguments:
    python main.py --api-key "key" --api-secret "secret"

    # Testnet mode:
    python main.py --testnet

    # Run once (for testing):
    python main.py --once

    # Custom symbols:
    python main.py --symbols BTCUSDT ETHUSDT

    # Disable Telegram notifications:
    python main.py --no-telegram
"""

import os
import sys
import signal
import logging
from typing import Optional

from donchian_breakout_strategy import DonchianBreakoutStrategy, StrategyConfig
from telegram_notifier import TelegramNotifier, create_notifier_from_env

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

# Global strategy instance for signal handling
strategy: Optional[DonchianBreakoutStrategy] = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    if strategy:
        strategy.stop()


def get_credentials():
    """Get API credentials from environment or raise error."""
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        return None, None

    return api_key, api_secret


def get_telegram_config():
    """Get Telegram configuration from environment."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return bot_token, chat_id


def print_banner():
    """Print startup banner."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║        DONCHIAN BREAKOUT TRADING BOT                        ║
║                                                              ║
║  Strategy: Trend-following with Donchian channel breakouts  ║
║  Markets:  BTCUSDT, ETHUSDT, SOLUSDT                        ║
║  Timeframe: 4H candles, checked every 30 minutes            ║
║                                                              ║
║  Risk: 1% per trade, max 3x leverage                        ║
║  Entries: Donchian 55 breakouts with EMA trend filters      ║
║  Exits: Trailing stop (10-period low/high)                  ║
║  Pyramiding: Up to 4 additions on +1.5 ATR moves            ║
╚══════════════════════════════════════════════════════════════╝
    """)


def main():
    """Main entry point."""
    global strategy

    import argparse

    parser = argparse.ArgumentParser(
        description="Donchian Breakout Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          Run with env vars
  python main.py --testnet                Use testnet
  python main.py --once                   Single run (no loop)
  python main.py --symbols BTCUSDT        Trade only BTC
  python main.py --no-telegram            Disable Telegram notifications

Telegram Setup:
  1. Create a bot with @BotFather on Telegram
  2. Get your chat ID by messaging @userinfobot
  3. Set environment variables:
     export TELEGRAM_BOT_TOKEN="your_bot_token"
     export TELEGRAM_CHAT_ID="your_chat_id"
        """
    )
    parser.add_argument(
        "--api-key",
        help="Binance API key (or set BINANCE_API_KEY env var)"
    )
    parser.add_argument(
        "--api-secret",
        help="Binance API secret (or set BINANCE_API_SECRET env var)"
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use Binance testnet instead of production"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (useful for testing)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        help="Symbols to trade (default: BTCUSDT ETHUSDT SOLUSDT)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Check interval in seconds (default: 1800 = 30 min)"
    )
    parser.add_argument(
        "--risk",
        type=float,
        default=0.01,
        help="Risk per trade as decimal (default: 0.01 = 1%%)"
    )
    parser.add_argument(
        "--leverage",
        type=int,
        default=3,
        help="Maximum leverage (default: 3)"
    )
    # Telegram arguments
    parser.add_argument(
        "--telegram-token",
        help="Telegram bot token (or set TELEGRAM_BOT_TOKEN env var)"
    )
    parser.add_argument(
        "--telegram-chat-id",
        help="Telegram chat ID (or set TELEGRAM_CHAT_ID env var)"
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Disable Telegram notifications"
    )
    parser.add_argument(
        "--telegram-silent",
        action="store_true",
        help="Send Telegram messages silently (no notification sound)"
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a test Telegram message and exit"
    )

    args = parser.parse_args()

    # Print banner
    print_banner()

    # Get credentials
    api_key = args.api_key
    api_secret = args.api_secret

    if not api_key or not api_secret:
        api_key, api_secret = get_credentials()

    if not api_key or not api_secret:
        logger.error(
            "API credentials required. Set BINANCE_API_KEY and BINANCE_API_SECRET "
            "environment variables or use --api-key and --api-secret arguments."
        )
        sys.exit(1)

    # Set up Telegram notifier
    notifier = None
    if not args.no_telegram:
        telegram_token = args.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = args.telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if telegram_token and telegram_chat_id:
            notifier = TelegramNotifier(
                bot_token=telegram_token,
                chat_id=telegram_chat_id,
                enabled=True,
                silent=args.telegram_silent
            )
            logger.info("Telegram notifications enabled")

            # Test telegram if requested
            if args.test_telegram:
                logger.info("Testing Telegram connection...")
                if notifier.test_connection():
                    logger.info("Telegram test message sent successfully!")
                else:
                    logger.error("Failed to send Telegram test message")
                sys.exit(0)
        else:
            logger.info(
                "Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
                "environment variables to enable notifications."
            )
    else:
        logger.info("Telegram notifications disabled via --no-telegram")

    # Create configuration
    config = StrategyConfig(
        symbols=args.symbols,
        check_interval_seconds=args.interval,
        risk_per_trade=args.risk,
        max_leverage=args.leverage
    )

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create strategy
    strategy = DonchianBreakoutStrategy(
        api_key=api_key,
        api_secret=api_secret,
        config=config,
        testnet=args.testnet,
        notifier=notifier
    )

    # Log configuration
    logger.info(f"Configuration:")
    logger.info(f"  Symbols: {config.symbols}")
    logger.info(f"  Check interval: {config.check_interval_seconds}s ({config.check_interval_seconds // 60} min)")
    logger.info(f"  Risk per trade: {config.risk_per_trade * 100}%")
    logger.info(f"  Max leverage: {config.max_leverage}x")
    logger.info(f"  Volatility threshold: {config.volatility_threshold * 100}%")
    logger.info(f"  ATR stop multiplier: {config.atr_stop_multiplier}x")
    logger.info(f"  Pyramid ATR multiplier: {config.pyramid_atr_multiplier}x")
    logger.info(f"  Max pyramids: {config.max_pyramid_additions}")
    logger.info(f"  Min balance for SOL: ${config.min_balance_for_sol}")
    logger.info(f"  Min balance for trading: ${config.min_balance_for_trading}")
    logger.info(f"  Testnet: {args.testnet}")
    logger.info(f"  Telegram: {'Enabled' if notifier else 'Disabled'}")

    # Run strategy
    if args.once:
        logger.info("Running single iteration...")
        strategy.run_once()
    else:
        logger.info("Starting continuous trading loop...")
        strategy.run()

    logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    main()
