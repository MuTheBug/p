"""
Telegram Notification Module

Sends trading bot notifications to Telegram.
Supports formatted messages with emojis for different event types.

Setup:
1. Create a bot with @BotFather on Telegram
2. Get your chat ID by messaging @userinfobot
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables
"""

import requests
import logging
from typing import Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications with their emoji prefixes."""
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    ENTRY_LONG = "🟢"
    ENTRY_SHORT = "🔴"
    EXIT = "🏁"
    PYRAMID = "📈"
    PROFIT = "💰"
    LOSS = "📉"
    STARTUP = "🚀"
    SHUTDOWN = "🛑"
    BALANCE = "💵"
    SIGNAL = "🔔"


class TelegramNotifier:
    """
    Telegram notification handler for trading bot.

    Usage:
        notifier = TelegramNotifier(bot_token, chat_id)
        notifier.send_entry("BTCUSDT", "LONG", 0.01, 50000.0, 1000.0)
    """

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        enabled: bool = True,
        silent: bool = False
    ):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Telegram chat ID to send messages to
            enabled: Whether notifications are enabled
            silent: Send messages silently (no notification sound)
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.silent = silent
        self.api_url = self.TELEGRAM_API_URL.format(token=bot_token)

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to Telegram.

        Args:
            text: Message text (supports HTML formatting)
            parse_mode: Parse mode (HTML or Markdown)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return True

        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram not configured, skipping notification")
            return False

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": self.silent
            }

            response = requests.post(self.api_url, json=payload, timeout=10)

            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram API error: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.Timeout:
            logger.warning("Telegram notification timeout")
            return False
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
            return False

    def _format_price(self, price: float) -> str:
        """Format price with appropriate precision."""
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        else:
            return f"${price:.6f}"

    def _format_quantity(self, qty: float, symbol: str) -> str:
        """Format quantity based on symbol."""
        if "BTC" in symbol:
            return f"{qty:.4f}"
        elif "ETH" in symbol:
            return f"{qty:.3f}"
        else:
            return f"{qty:.2f}"

    def _format_pnl(self, pnl: float) -> str:
        """Format PnL with color indicator."""
        if pnl >= 0:
            return f"+${pnl:.2f} 💚"
        else:
            return f"-${abs(pnl):.2f} 💔"

    def _get_timestamp(self) -> str:
        """Get formatted timestamp."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    # ==================== Notification Methods ====================

    def send_startup(self, symbols: list, balance: float, testnet: bool = False) -> bool:
        """Send bot startup notification."""
        mode = "🧪 TESTNET" if testnet else "🔴 LIVE"
        symbols_str = ", ".join(symbols)

        message = f"""
{NotificationType.STARTUP.value} <b>Trading Bot Started</b>

{mode}
<b>Symbols:</b> {symbols_str}
<b>Balance:</b> ${balance:,.2f} USDT
<b>Time:</b> {self._get_timestamp()}

Bot is now monitoring markets...
"""
        return self._send_message(message.strip())

    def send_shutdown(self, reason: str = "Manual stop") -> bool:
        """Send bot shutdown notification."""
        message = f"""
{NotificationType.SHUTDOWN.value} <b>Trading Bot Stopped</b>

<b>Reason:</b> {reason}
<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_entry(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_distance: float,
        risk_amount: float
    ) -> bool:
        """Send position entry notification."""
        emoji = NotificationType.ENTRY_LONG.value if side == "LONG" else NotificationType.ENTRY_SHORT.value
        direction = "📈 LONG" if side == "LONG" else "📉 SHORT"

        notional = quantity * price

        message = f"""
{emoji} <b>New Position Opened</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Quantity:</b> {self._format_quantity(quantity, symbol)}
<b>Entry Price:</b> {self._format_price(price)}
<b>Notional:</b> ${notional:,.2f}
<b>Risk:</b> ${risk_amount:.2f}
<b>Stop Distance:</b> {self._format_price(stop_distance)}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_exit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str
    ) -> bool:
        """Send position exit notification."""
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        if side == "SHORT":
            pnl_pct = -pnl_pct

        emoji = NotificationType.PROFIT.value if pnl >= 0 else NotificationType.LOSS.value

        message = f"""
{NotificationType.EXIT.value} <b>Position Closed</b>

<b>Symbol:</b> {symbol}
<b>Side:</b> {side}
<b>Quantity:</b> {self._format_quantity(quantity, symbol)}
<b>Entry:</b> {self._format_price(entry_price)}
<b>Exit:</b> {self._format_price(exit_price)}
<b>PnL:</b> {self._format_pnl(pnl)} ({pnl_pct:+.2f}%)
<b>Reason:</b> {reason}

{emoji} <b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_pyramid(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        pyramid_number: int,
        total_positions: int
    ) -> bool:
        """Send pyramid (add to position) notification."""
        message = f"""
{NotificationType.PYRAMID.value} <b>Pyramid #{pyramid_number}</b>

<b>Symbol:</b> {symbol}
<b>Side:</b> {side}
<b>Added:</b> {self._format_quantity(quantity, symbol)}
<b>Price:</b> {self._format_price(price)}
<b>Total Positions:</b> {total_positions}/5

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_signal(
        self,
        symbol: str,
        signal_type: str,
        reason: str
    ) -> bool:
        """Send entry signal detection notification."""
        emoji = NotificationType.ENTRY_LONG.value if signal_type == "LONG" else NotificationType.ENTRY_SHORT.value

        message = f"""
{NotificationType.SIGNAL.value} <b>Signal Detected</b>

<b>Symbol:</b> {symbol}
<b>Signal:</b> {emoji} {signal_type}
<b>Reason:</b> {reason}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_trailing_stop_update(
        self,
        symbol: str,
        side: str,
        current_price: float,
        trailing_stop: float
    ) -> bool:
        """Send trailing stop level notification (optional, can be noisy)."""
        distance_pct = abs(current_price - trailing_stop) / current_price * 100

        message = f"""
{NotificationType.INFO.value} <b>Trailing Stop Update</b>

<b>Symbol:</b> {symbol}
<b>Side:</b> {side}
<b>Current Price:</b> {self._format_price(current_price)}
<b>Trailing Stop:</b> {self._format_price(trailing_stop)}
<b>Distance:</b> {distance_pct:.2f}%
"""
        return self._send_message(message.strip())

    def send_balance_update(
        self,
        balance: float,
        available: float,
        open_positions: int
    ) -> bool:
        """Send periodic balance update."""
        message = f"""
{NotificationType.BALANCE.value} <b>Balance Update</b>

<b>Total Balance:</b> ${balance:,.2f}
<b>Available:</b> ${available:,.2f}
<b>Open Positions:</b> {open_positions}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_error(self, symbol: str, error_message: str) -> bool:
        """Send error notification."""
        message = f"""
{NotificationType.ERROR.value} <b>Error</b>

<b>Symbol:</b> {symbol}
<b>Error:</b> {error_message}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_warning(self, message_text: str) -> bool:
        """Send warning notification."""
        message = f"""
{NotificationType.WARNING.value} <b>Warning</b>

{message_text}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_info(self, title: str, details: str) -> bool:
        """Send info notification."""
        message = f"""
{NotificationType.INFO.value} <b>{title}</b>

{details}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_daily_summary(
        self,
        balance: float,
        daily_pnl: float,
        trades_today: int,
        open_positions: list
    ) -> bool:
        """Send daily summary notification."""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

        positions_str = ""
        if open_positions:
            for pos in open_positions:
                positions_str += f"\n  • {pos['symbol']}: {pos['side']} ({pos['pnl']:+.2f})"
        else:
            positions_str = "\n  None"

        message = f"""
📊 <b>Daily Summary</b>

<b>Balance:</b> ${balance:,.2f}
<b>Daily PnL:</b> {pnl_emoji} {self._format_pnl(daily_pnl)}
<b>Trades Today:</b> {trades_today}

<b>Open Positions:</b>{positions_str}

<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())

    def send_custom(self, message: str) -> bool:
        """Send a custom message."""
        return self._send_message(message)

    def test_connection(self) -> bool:
        """Test Telegram connection."""
        message = f"""
{NotificationType.SUCCESS.value} <b>Connection Test</b>

Telegram notifications are working!
<b>Time:</b> {self._get_timestamp()}
"""
        return self._send_message(message.strip())


# ==================== Utility Functions ====================

def create_notifier_from_env() -> Optional[TelegramNotifier]:
    """
    Create a TelegramNotifier from environment variables.

    Returns:
        TelegramNotifier if configured, None otherwise
    """
    import os

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.info("Telegram not configured (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set)")
        return None

    return TelegramNotifier(bot_token, chat_id)
