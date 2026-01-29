"""
Telegram Notification Service for Trading Bot

Provides asynchronous and synchronous methods for sending trade notifications,
alerts, and status updates via Telegram Bot API.
"""

import requests
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import threading
from queue import Queue


class NotificationType(Enum):
    """Types of trading notifications."""
    TRADE_ENTRY = "TRADE_ENTRY"
    TRADE_EXIT = "TRADE_EXIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TAKE_PROFIT_HIT = "TAKE_PROFIT_HIT"
    TRAILING_STOP_MOVED = "TRAILING_STOP_MOVED"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    POSITION_UPDATE = "POSITION_UPDATE"
    ACCOUNT_UPDATE = "ACCOUNT_UPDATE"


@dataclass
class TradeNotification:
    """Trade notification data structure."""
    notification_type: NotificationType
    symbol: str
    side: str
    quantity: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    strategy: Optional[str] = None
    setup_type: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class TelegramNotifier:
    """
    Telegram notification service for trading bot.

    Sends formatted notifications about trade entries, exits, signals,
    and other trading events via Telegram Bot API.

    Features:
    - Synchronous and asynchronous message sending
    - Message queue for non-blocking notifications
    - Rate limiting to avoid Telegram API limits
    - Rich formatting with trade details
    - Error handling and retry logic

    Args:
        bot_token: Telegram Bot API token (from @BotFather)
        chat_id: Target chat ID or channel username
        rate_limit: Minimum seconds between messages (default: 1.0)
        max_retries: Maximum retry attempts for failed sends (default: 3)
        async_mode: Use background thread for sending (default: True)

    Example:
        >>> notifier = TelegramNotifier(
        ...     bot_token="123456:ABC-DEF...",
        ...     chat_id="@my_channel"
        ... )
        >>> notifier.send_trade_entry(
        ...     symbol="BTCUSDT",
        ...     side="BUY",
        ...     quantity=0.01,
        ...     entry_price=42000,
        ...     stop_loss=41000,
        ...     take_profit=45000
        ... )
    """

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        rate_limit: float = 1.0,
        max_retries: int = 3,
        async_mode: bool = True
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self.async_mode = async_mode

        self.base_url = self.BASE_URL.format(token=bot_token)
        self._last_send_time = 0
        self._message_queue: Queue = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        if self.async_mode:
            self._start_worker()

    def _start_worker(self):
        """Start background worker thread for async message sending."""
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _worker_loop(self):
        """Background worker loop for processing message queue."""
        while self._running:
            try:
                if not self._message_queue.empty():
                    message, parse_mode, disable_preview = self._message_queue.get(timeout=1)
                    self._send_message_sync(message, parse_mode, disable_preview)
                    self._message_queue.task_done()
                else:
                    time.sleep(0.1)
            except Exception:
                pass

    def stop(self):
        """Stop the async worker thread."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _enforce_rate_limit(self):
        """Enforce rate limiting between messages."""
        current_time = time.time()
        elapsed = current_time - self._last_send_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_send_time = time.time()

    def _send_message_sync(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_preview: bool = True
    ) -> bool:
        """
        Send message synchronously with retry logic.

        Args:
            message: Message text to send
            parse_mode: Parse mode (HTML, Markdown, MarkdownV2)
            disable_preview: Disable link previews

        Returns:
            True if sent successfully, False otherwise
        """
        self._enforce_rate_limit()

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, json=payload, timeout=10)
                data = response.json()

                if data.get("ok"):
                    return True

                error_code = data.get("error_code", 0)
                if error_code == 429:  # Rate limited
                    retry_after = data.get("parameters", {}).get("retry_after", 5)
                    time.sleep(retry_after)
                    continue

                return False

            except requests.RequestException:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue

        return False

    def send_message(
        self,
        message: str,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
        force_sync: bool = False
    ) -> bool:
        """
        Send a message via Telegram.

        Args:
            message: Message text to send
            parse_mode: Parse mode (HTML, Markdown, MarkdownV2)
            disable_preview: Disable link previews
            force_sync: Force synchronous sending even in async mode

        Returns:
            True if queued/sent successfully
        """
        if self.async_mode and not force_sync:
            self._message_queue.put((message, parse_mode, disable_preview))
            return True
        else:
            return self._send_message_sync(message, parse_mode, disable_preview)

    def _format_price(self, price: Optional[float]) -> str:
        """Format price for display."""
        if price is None:
            return "N/A"
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        else:
            return f"${price:.8f}"

    def _format_pnl(self, pnl: Optional[float], pnl_percent: Optional[float]) -> str:
        """Format PnL for display."""
        if pnl is None:
            return ""

        emoji = "+" if pnl >= 0 else ""
        pnl_str = f"{emoji}${pnl:,.2f}"

        if pnl_percent is not None:
            emoji = "+" if pnl_percent >= 0 else ""
            pnl_str += f" ({emoji}{pnl_percent:.2f}%)"

        return pnl_str

    def _get_side_emoji(self, side: str) -> str:
        """Get emoji for trade side."""
        return "🟢" if side.upper() == "BUY" else "🔴"

    def _get_notification_emoji(self, notification_type: NotificationType) -> str:
        """Get emoji for notification type."""
        emoji_map = {
            NotificationType.TRADE_ENTRY: "📈",
            NotificationType.TRADE_EXIT: "📉",
            NotificationType.STOP_LOSS_HIT: "🛑",
            NotificationType.TAKE_PROFIT_HIT: "🎯",
            NotificationType.TRAILING_STOP_MOVED: "📊",
            NotificationType.SIGNAL_DETECTED: "🔔",
            NotificationType.ERROR: "❌",
            NotificationType.WARNING: "⚠️",
            NotificationType.INFO: "ℹ️",
            NotificationType.POSITION_UPDATE: "📋",
            NotificationType.ACCOUNT_UPDATE: "💰",
        }
        return emoji_map.get(notification_type, "📌")

    def send_trade_entry(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        strategy: Optional[str] = None,
        setup_type: Optional[str] = None,
        leverage: Optional[int] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send trade entry notification.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Trade side ("BUY" or "SELL")
            quantity: Position quantity
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            strategy: Strategy name
            setup_type: Setup type (e.g., "Trendline Bounce")
            leverage: Position leverage
            additional_info: Additional details to include

        Returns:
            True if notification sent/queued successfully
        """
        side_emoji = self._get_side_emoji(side)
        entry_emoji = self._get_notification_emoji(NotificationType.TRADE_ENTRY)

        message = f"{entry_emoji} <b>TRADE ENTRY</b> {side_emoji}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>Symbol:</b> {symbol}\n"
        message += f"<b>Side:</b> {side.upper()}\n"
        message += f"<b>Quantity:</b> {quantity}\n"
        message += f"<b>Entry Price:</b> {self._format_price(entry_price)}\n"

        if leverage:
            message += f"<b>Leverage:</b> {leverage}x\n"

        if stop_loss:
            sl_distance = abs(entry_price - stop_loss) / entry_price * 100
            message += f"<b>Stop Loss:</b> {self._format_price(stop_loss)} ({sl_distance:.2f}%)\n"

        if take_profit:
            tp_distance = abs(take_profit - entry_price) / entry_price * 100
            message += f"<b>Take Profit:</b> {self._format_price(take_profit)} ({tp_distance:.2f}%)\n"

        if stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            if risk > 0:
                rr_ratio = reward / risk
                message += f"<b>Risk/Reward:</b> 1:{rr_ratio:.2f}\n"

        if strategy:
            message += f"\n<b>Strategy:</b> {strategy}\n"

        if setup_type:
            message += f"<b>Setup:</b> {setup_type}\n"

        if additional_info:
            message += f"\n<b>Details:</b>\n"
            for key, value in additional_info.items():
                message += f"  • {key}: {value}\n"

        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_trade_exit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: Optional[float] = None,
        pnl_percent: Optional[float] = None,
        exit_reason: str = "Manual",
        strategy: Optional[str] = None,
        duration: Optional[str] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send trade exit notification.

        Args:
            symbol: Trading symbol
            side: Original trade side
            quantity: Position quantity
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/loss in USD
            pnl_percent: Profit/loss percentage
            exit_reason: Reason for exit
            strategy: Strategy name
            duration: Trade duration string
            additional_info: Additional details

        Returns:
            True if notification sent/queued successfully
        """
        is_profit = pnl is not None and pnl >= 0
        result_emoji = "✅" if is_profit else "❌"

        if exit_reason == "Stop Loss":
            notification_type = NotificationType.STOP_LOSS_HIT
        elif exit_reason == "Take Profit":
            notification_type = NotificationType.TAKE_PROFIT_HIT
        else:
            notification_type = NotificationType.TRADE_EXIT

        type_emoji = self._get_notification_emoji(notification_type)

        message = f"{type_emoji} <b>TRADE EXIT</b> {result_emoji}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>Symbol:</b> {symbol}\n"
        message += f"<b>Side:</b> {side.upper()}\n"
        message += f"<b>Quantity:</b> {quantity}\n"
        message += f"<b>Entry:</b> {self._format_price(entry_price)}\n"
        message += f"<b>Exit:</b> {self._format_price(exit_price)}\n"
        message += f"<b>Exit Reason:</b> {exit_reason}\n"

        if pnl is not None:
            pnl_formatted = self._format_pnl(pnl, pnl_percent)
            message += f"\n<b>{'Profit' if is_profit else 'Loss'}:</b> {pnl_formatted}\n"

        if duration:
            message += f"<b>Duration:</b> {duration}\n"

        if strategy:
            message += f"\n<b>Strategy:</b> {strategy}\n"

        if additional_info:
            message += f"\n<b>Details:</b>\n"
            for key, value in additional_info.items():
                message += f"  • {key}: {value}\n"

        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_signal_alert(
        self,
        symbol: str,
        signal_type: str,
        direction: str,
        price: float,
        strategy: Optional[str] = None,
        setup_details: Optional[Dict[str, Any]] = None,
        action_required: bool = True
    ) -> bool:
        """
        Send trading signal alert.

        Args:
            symbol: Trading symbol
            signal_type: Type of signal (e.g., "Trendline Bounce", "Trendline Break")
            direction: Signal direction ("LONG" or "SHORT")
            price: Current price
            strategy: Strategy name
            setup_details: Setup details dictionary
            action_required: Whether user action is required

        Returns:
            True if notification sent/queued successfully
        """
        emoji = self._get_notification_emoji(NotificationType.SIGNAL_DETECTED)
        dir_emoji = "🟢" if direction.upper() == "LONG" else "🔴"

        message = f"{emoji} <b>SIGNAL DETECTED</b> {dir_emoji}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>Symbol:</b> {symbol}\n"
        message += f"<b>Signal:</b> {signal_type}\n"
        message += f"<b>Direction:</b> {direction.upper()}\n"
        message += f"<b>Price:</b> {self._format_price(price)}\n"

        if strategy:
            message += f"<b>Strategy:</b> {strategy}\n"

        if setup_details:
            message += f"\n<b>Setup Details:</b>\n"
            for key, value in setup_details.items():
                message += f"  • {key}: {value}\n"

        if action_required:
            message += f"\n⚡ <b>Action Required</b>"

        message += f"\n\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_stop_update(
        self,
        symbol: str,
        side: str,
        old_stop: float,
        new_stop: float,
        current_price: float,
        reason: str = "Trailing"
    ) -> bool:
        """
        Send stop loss update notification.

        Args:
            symbol: Trading symbol
            side: Trade side
            old_stop: Previous stop loss price
            new_stop: New stop loss price
            current_price: Current market price
            reason: Reason for update

        Returns:
            True if notification sent/queued successfully
        """
        emoji = self._get_notification_emoji(NotificationType.TRAILING_STOP_MOVED)

        message = f"{emoji} <b>STOP UPDATED</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>Symbol:</b> {symbol}\n"
        message += f"<b>Side:</b> {side.upper()}\n"
        message += f"<b>Old Stop:</b> {self._format_price(old_stop)}\n"
        message += f"<b>New Stop:</b> {self._format_price(new_stop)}\n"
        message += f"<b>Current Price:</b> {self._format_price(current_price)}\n"
        message += f"<b>Reason:</b> {reason}\n"
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_error(
        self,
        error_message: str,
        context: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> bool:
        """
        Send error notification.

        Args:
            error_message: Error message
            context: Context where error occurred
            symbol: Related symbol if applicable

        Returns:
            True if notification sent/queued successfully
        """
        emoji = self._get_notification_emoji(NotificationType.ERROR)

        message = f"{emoji} <b>ERROR</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"

        if symbol:
            message += f"<b>Symbol:</b> {symbol}\n"

        if context:
            message += f"<b>Context:</b> {context}\n"

        message += f"<b>Error:</b> {error_message}\n"
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_warning(
        self,
        warning_message: str,
        context: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> bool:
        """
        Send warning notification.

        Args:
            warning_message: Warning message
            context: Context where warning occurred
            symbol: Related symbol if applicable

        Returns:
            True if notification sent/queued successfully
        """
        emoji = self._get_notification_emoji(NotificationType.WARNING)

        message = f"{emoji} <b>WARNING</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"

        if symbol:
            message += f"<b>Symbol:</b> {symbol}\n"

        if context:
            message += f"<b>Context:</b> {context}\n"

        message += f"<b>Warning:</b> {warning_message}\n"
        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_account_summary(
        self,
        total_balance: float,
        available_balance: float,
        unrealized_pnl: float,
        daily_pnl: Optional[float] = None,
        open_positions: int = 0,
        margin_ratio: Optional[float] = None
    ) -> bool:
        """
        Send account summary notification.

        Args:
            total_balance: Total wallet balance
            available_balance: Available margin balance
            unrealized_pnl: Unrealized PnL
            daily_pnl: Daily realized PnL
            open_positions: Number of open positions
            margin_ratio: Current margin ratio percentage

        Returns:
            True if notification sent/queued successfully
        """
        emoji = self._get_notification_emoji(NotificationType.ACCOUNT_UPDATE)

        message = f"{emoji} <b>ACCOUNT SUMMARY</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"<b>Total Balance:</b> ${total_balance:,.2f}\n"
        message += f"<b>Available:</b> ${available_balance:,.2f}\n"

        pnl_emoji = "📈" if unrealized_pnl >= 0 else "📉"
        message += f"<b>Unrealized PnL:</b> {pnl_emoji} {self._format_pnl(unrealized_pnl, None)}\n"

        if daily_pnl is not None:
            daily_emoji = "📈" if daily_pnl >= 0 else "📉"
            message += f"<b>Daily PnL:</b> {daily_emoji} {self._format_pnl(daily_pnl, None)}\n"

        message += f"<b>Open Positions:</b> {open_positions}\n"

        if margin_ratio is not None:
            ratio_emoji = "🟢" if margin_ratio < 50 else "🟡" if margin_ratio < 80 else "🔴"
            message += f"<b>Margin Ratio:</b> {ratio_emoji} {margin_ratio:.2f}%\n"

        message += f"\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def send_custom(
        self,
        title: str,
        body: str,
        emoji: str = "📌"
    ) -> bool:
        """
        Send custom notification with title and body.

        Args:
            title: Notification title
            body: Notification body
            emoji: Emoji to use

        Returns:
            True if notification sent/queued successfully
        """
        message = f"{emoji} <b>{title}</b>\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += body
        message += f"\n\n<i>🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"

        return self.send_message(message)

    def test_connection(self) -> bool:
        """
        Test Telegram bot connection by sending a test message.

        Returns:
            True if connection is working
        """
        return self.send_message(
            "🤖 <b>Bot Connected</b>\n\nTradingBot notification service is active.",
            force_sync=True
        )

    def get_bot_info(self) -> Optional[Dict[str, Any]]:
        """
        Get bot information from Telegram API.

        Returns:
            Bot info dict or None if failed
        """
        try:
            response = requests.get(
                f"{self.base_url}/getMe",
                timeout=10
            )
            data = response.json()
            if data.get("ok"):
                return data.get("result")
        except requests.RequestException:
            pass
        return None
