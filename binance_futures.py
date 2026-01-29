"""
Binance Futures Trading Client

A comprehensive Python class for placing all types of orders on Binance Futures.
Supports all order types, position management, leverage, and account operations.
"""

import hashlib
import hmac
import time
import requests
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
from dataclasses import dataclass
from urllib.parse import urlencode


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """All supported order types in Binance Futures."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class TimeInForce(Enum):
    """Time in force options."""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTX = "GTX"  # Post Only (Good Till Crossing)


class PositionSide(Enum):
    """Position side for hedge mode."""
    BOTH = "BOTH"  # One-way mode
    LONG = "LONG"  # Hedge mode long
    SHORT = "SHORT"  # Hedge mode short


class MarginType(Enum):
    """Margin type enumeration."""
    ISOLATED = "ISOLATED"
    CROSSED = "CROSSED"


class WorkingType(Enum):
    """Price type for stop orders."""
    MARK_PRICE = "MARK_PRICE"
    CONTRACT_PRICE = "CONTRACT_PRICE"


class ResponseType(Enum):
    """Response type for orders."""
    ACK = "ACK"
    RESULT = "RESULT"


class IncomeType(Enum):
    """Income history types."""
    TRANSFER = "TRANSFER"
    WELCOME_BONUS = "WELCOME_BONUS"
    REALIZED_PNL = "REALIZED_PNL"
    FUNDING_FEE = "FUNDING_FEE"
    COMMISSION = "COMMISSION"
    INSURANCE_CLEAR = "INSURANCE_CLEAR"
    REFERRAL_KICKBACK = "REFERRAL_KICKBACK"
    COMMISSION_REBATE = "COMMISSION_REBATE"
    API_REBATE = "API_REBATE"
    CONTEST_REWARD = "CONTEST_REWARD"
    CROSS_COLLATERAL_TRANSFER = "CROSS_COLLATERAL_TRANSFER"
    OPTIONS_PREMIUM_FEE = "OPTIONS_PREMIUM_FEE"
    OPTIONS_SETTLE_PROFIT = "OPTIONS_SETTLE_PROFIT"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER"
    AUTO_EXCHANGE = "AUTO_EXCHANGE"
    DELIVERED_SETTELMENT = "DELIVERED_SETTELMENT"
    COIN_SWAP_DEPOSIT = "COIN_SWAP_DEPOSIT"
    COIN_SWAP_WITHDRAW = "COIN_SWAP_WITHDRAW"
    POSITION_LIMIT_INCREASE_FEE = "POSITION_LIMIT_INCREASE_FEE"


class AlgoOrderType(Enum):
    """Algo order types for conditional orders (post Dec 2025 migration)."""
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TRAILING_STOP_MARKET = "TRAILING_STOP_MARKET"


class VPUrgency(Enum):
    """Urgency levels for Volume Participation (VP) orders."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlgoType(Enum):
    """Algorithm types."""
    TWAP = "TWAP"
    VP = "VP"


@dataclass
class OrderResult:
    """Order result dataclass."""
    order_id: int
    symbol: str
    status: str
    client_order_id: str
    price: str
    avg_price: str
    orig_qty: str
    executed_qty: str
    cum_qty: str
    cum_quote: str
    time_in_force: str
    order_type: str
    reduce_only: bool
    close_position: bool
    side: str
    position_side: str
    stop_price: str
    working_type: str
    price_protect: bool
    orig_type: str
    update_time: int
    raw_response: Dict[str, Any]

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "OrderResult":
        """Create OrderResult from API response."""
        return cls(
            order_id=response.get("orderId", 0),
            symbol=response.get("symbol", ""),
            status=response.get("status", ""),
            client_order_id=response.get("clientOrderId", ""),
            price=response.get("price", "0"),
            avg_price=response.get("avgPrice", "0"),
            orig_qty=response.get("origQty", "0"),
            executed_qty=response.get("executedQty", "0"),
            cum_qty=response.get("cumQty", "0"),
            cum_quote=response.get("cumQuote", "0"),
            time_in_force=response.get("timeInForce", ""),
            order_type=response.get("type", ""),
            reduce_only=response.get("reduceOnly", False),
            close_position=response.get("closePosition", False),
            side=response.get("side", ""),
            position_side=response.get("positionSide", ""),
            stop_price=response.get("stopPrice", "0"),
            working_type=response.get("workingType", ""),
            price_protect=response.get("priceProtect", False),
            orig_type=response.get("origType", ""),
            update_time=response.get("updateTime", 0),
            raw_response=response
        )


@dataclass
class AlgoOrderResult:
    """Algo order result dataclass for conditional orders (post Dec 2025)."""
    algo_id: int
    symbol: str
    side: str
    position_side: str
    quantity: str
    order_type: str
    stop_price: str
    activation_price: str
    callback_rate: str
    working_type: str
    price_protect: bool
    reduce_only: bool
    close_position: bool
    status: str
    triggered_price: str
    book_time: int
    update_time: int
    raw_response: Dict[str, Any]

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "AlgoOrderResult":
        """Create AlgoOrderResult from API response."""
        return cls(
            algo_id=response.get("algoId", 0),
            symbol=response.get("symbol", ""),
            side=response.get("side", ""),
            position_side=response.get("positionSide", ""),
            quantity=response.get("origQty", response.get("quantity", "0")),
            order_type=response.get("type", ""),
            stop_price=response.get("stopPrice", "0"),
            activation_price=response.get("activationPrice", "0"),
            callback_rate=response.get("callbackRate", "0"),
            working_type=response.get("workingType", ""),
            price_protect=response.get("priceProtect", False),
            reduce_only=response.get("reduceOnly", False),
            close_position=response.get("closePosition", False),
            status=response.get("status", response.get("algoStatus", "")),
            triggered_price=response.get("triggeredPrice", "0"),
            book_time=response.get("bookTime", 0),
            update_time=response.get("updateTime", 0),
            raw_response=response
        )


@dataclass
class TWAPOrderResult:
    """TWAP order result dataclass."""
    client_algo_id: str
    success: bool
    code: int
    msg: str
    raw_response: Dict[str, Any]

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "TWAPOrderResult":
        """Create TWAPOrderResult from API response."""
        return cls(
            client_algo_id=response.get("clientAlgoId", ""),
            success=response.get("success", False),
            code=response.get("code", 0),
            msg=response.get("msg", ""),
            raw_response=response
        )


@dataclass
class VPOrderResult:
    """VP (Volume Participation) order result dataclass."""
    client_algo_id: str
    success: bool
    code: int
    msg: str
    raw_response: Dict[str, Any]

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "VPOrderResult":
        """Create VPOrderResult from API response."""
        return cls(
            client_algo_id=response.get("clientAlgoId", ""),
            success=response.get("success", False),
            code=response.get("code", 0),
            msg=response.get("msg", ""),
            raw_response=response
        )


class BinanceFuturesError(Exception):
    """Custom exception for Binance Futures API errors."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance Error {code}: {message}")


class BinanceFuturesClient:
    """
    Comprehensive Binance Futures Trading Client.

    Supports all order types and trading functionalities:
    - Market, Limit orders (standard API)
    - Stop, Take Profit, Trailing Stop orders (Algo API - post Dec 2025)
    - TWAP (Time-Weighted Average Price) orders
    - VP (Volume Participation) orders
    - Position management (leverage, margin type, hedge mode)
    - Account operations (balance, positions, income history)
    - Batch orders and order management

    IMPORTANT: Since December 9, 2025, Binance migrated conditional orders
    (STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET)
    to the Algo Service API. Use the algo_* methods for these order types.

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Use testnet if True (default: False)
        recv_window: Request receive window in ms (default: 5000)

    Example:
        >>> client = BinanceFuturesClient(api_key="your_key", api_secret="your_secret")
        >>> # Place a market buy order
        >>> order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)
        >>> # Place a stop loss using the new Algo API
        >>> order = client.algo_stop_market_order("BTCUSDT", OrderSide.SELL, 0.01, stop_price=39000)
        >>> # Place a TWAP order (execute over 1 hour)
        >>> order = client.place_twap_order("BTCUSDT", OrderSide.BUY, 1.0, duration=3600)
    """

    # API Base URLs
    BASE_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://testnet.binancefuture.com"
    SAPI_URL = "https://api.binance.com"  # For TWAP/VP algo orders

    # API Endpoints
    ENDPOINTS = {
        # Trading (Standard Orders)
        "order": "/fapi/v1/order",
        "batch_orders": "/fapi/v1/batchOrders",
        "all_open_orders": "/fapi/v1/openOrders",
        "all_orders": "/fapi/v1/allOrders",
        "cancel_all_orders": "/fapi/v1/allOpenOrders",

        # Algo Orders - Conditional (post Dec 2025 migration)
        # These endpoints handle: STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
        "algo_order": "/fapi/v1/algoOrder",
        "algo_open_orders": "/fapi/v1/openAlgoOrders",
        "algo_all_orders": "/fapi/v1/allAlgoOrders",
        "algo_cancel_all": "/fapi/v1/algoOpenOrders",

        # Algo Orders - TWAP & VP (SAPI endpoints)
        "twap_new": "/sapi/v1/algo/futures/newOrderTwap",
        "vp_new": "/sapi/v1/algo/futures/newOrderVp",
        "algo_cancel": "/sapi/v1/algo/futures/order",
        "algo_sapi_open_orders": "/sapi/v1/algo/futures/openOrders",
        "algo_sapi_historical_orders": "/sapi/v1/algo/futures/historicalOrders",
        "algo_sapi_sub_orders": "/sapi/v1/algo/futures/subOrders",

        # Account
        "account": "/fapi/v2/account",
        "balance": "/fapi/v2/balance",
        "position_risk": "/fapi/v2/positionRisk",
        "income": "/fapi/v1/income",
        "leverage_bracket": "/fapi/v1/leverageBracket",

        # Position Settings
        "leverage": "/fapi/v1/leverage",
        "margin_type": "/fapi/v1/marginType",
        "position_margin": "/fapi/v1/positionMargin",
        "position_mode": "/fapi/v1/positionSide/dual",

        # Market Data
        "exchange_info": "/fapi/v1/exchangeInfo",
        "ticker_price": "/fapi/v1/ticker/price",
        "ticker_24hr": "/fapi/v1/ticker/24hr",
        "depth": "/fapi/v1/depth",
        "klines": "/fapi/v1/klines",
        "mark_price": "/fapi/v1/premiumIndex",
        "funding_rate": "/fapi/v1/fundingRate",

        # User Data Stream
        "listen_key": "/fapi/v1/listenKey",
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        recv_window: int = 5000
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        self.recv_window = recv_window
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        })

    # ==================== Authentication ====================

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for request."""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def _prepare_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters with timestamp and signature."""
        params = {k: v for k, v in params.items() if v is not None}
        params["timestamp"] = self._get_timestamp()
        params["recvWindow"] = self.recv_window
        params["signature"] = self._generate_signature(params)
        return params

    # ==================== Request Methods ====================

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True
    ) -> Dict[str, Any]:
        """Make HTTP request to Binance API."""
        url = f"{self.base_url}{endpoint}"
        params = params or {}

        if signed:
            params = self._prepare_params(params)

        try:
            if method == "GET":
                response = self.session.get(url, params=params)
            elif method == "POST":
                response = self.session.post(url, data=params)
            elif method == "PUT":
                response = self.session.put(url, data=params)
            elif method == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            result = response.json()

            if response.status_code >= 400:
                code = result.get("code", response.status_code)
                msg = result.get("msg", "Unknown error")
                raise BinanceFuturesError(code, msg)

            return result

        except requests.exceptions.RequestException as e:
            raise BinanceFuturesError(-1, f"Request failed: {str(e)}")

    def _get(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP GET request."""
        return self._request("GET", endpoint, params, signed)

    def _post(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP POST request."""
        return self._request("POST", endpoint, params, signed)

    def _put(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP PUT request."""
        return self._request("PUT", endpoint, params, signed)

    def _delete(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP DELETE request."""
        return self._request("DELETE", endpoint, params, signed)

    # ==================== SAPI Request Methods (for TWAP/VP) ====================

    def _sapi_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True
    ) -> Dict[str, Any]:
        """Make HTTP request to Binance SAPI (for TWAP/VP algo orders)."""
        url = f"{self.SAPI_URL}{endpoint}"
        params = params or {}

        if signed:
            params = self._prepare_params(params)

        try:
            if method == "GET":
                response = self.session.get(url, params=params)
            elif method == "POST":
                response = self.session.post(url, data=params)
            elif method == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            result = response.json()

            if response.status_code >= 400:
                code = result.get("code", response.status_code)
                msg = result.get("msg", "Unknown error")
                raise BinanceFuturesError(code, msg)

            return result

        except requests.exceptions.RequestException as e:
            raise BinanceFuturesError(-1, f"Request failed: {str(e)}")

    def _sapi_get(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP GET request to SAPI."""
        return self._sapi_request("GET", endpoint, params, signed)

    def _sapi_post(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP POST request to SAPI."""
        return self._sapi_request("POST", endpoint, params, signed)

    def _sapi_delete(self, endpoint: str, params: Optional[Dict] = None, signed: bool = True) -> Dict:
        """HTTP DELETE request to SAPI."""
        return self._sapi_request("DELETE", endpoint, params, signed)

    # ==================== Order Placement ====================

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        position_side: PositionSide = PositionSide.BOTH,
        reduce_only: Optional[bool] = None,
        close_position: Optional[bool] = None,
        activation_price: Optional[float] = None,
        callback_rate: Optional[float] = None,
        working_type: Optional[WorkingType] = None,
        price_protect: Optional[bool] = None,
        new_client_order_id: Optional[str] = None,
        response_type: ResponseType = ResponseType.RESULT
    ) -> OrderResult:
        """
        Place a new order on Binance Futures.

        This is the core order placement method that supports all order types.
        For convenience, use the specific order methods (market_order, limit_order, etc.)

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            order_type: Order type (MARKET, LIMIT, STOP, etc.)
            quantity: Order quantity (not required if close_position=True)
            price: Limit price (required for LIMIT orders)
            stop_price: Stop/trigger price (required for STOP orders)
            time_in_force: Time in force (GTC, IOC, FOK, GTX)
            position_side: Position side for hedge mode (BOTH, LONG, SHORT)
            reduce_only: Reduce only flag (cannot be used with close_position)
            close_position: Close entire position (cannot be used with quantity)
            activation_price: Activation price for trailing stop
            callback_rate: Callback rate for trailing stop (0.1 to 5)
            working_type: Price type for stop orders (MARK_PRICE or CONTRACT_PRICE)
            price_protect: Price protection flag
            new_client_order_id: Custom client order ID
            response_type: Response type (ACK or RESULT)

        Returns:
            OrderResult object with order details

        Raises:
            BinanceFuturesError: If order placement fails
        """
        params = {
            "symbol": symbol.upper(),
            "side": side.value if isinstance(side, OrderSide) else side,
            "type": order_type.value if isinstance(order_type, OrderType) else order_type,
            "newOrderRespType": response_type.value if isinstance(response_type, ResponseType) else response_type,
        }

        if quantity is not None:
            params["quantity"] = str(quantity)

        if price is not None:
            params["price"] = str(price)

        if stop_price is not None:
            params["stopPrice"] = str(stop_price)

        if time_in_force is not None:
            params["timeInForce"] = time_in_force.value if isinstance(time_in_force, TimeInForce) else time_in_force

        if position_side != PositionSide.BOTH:
            params["positionSide"] = position_side.value if isinstance(position_side, PositionSide) else position_side
        else:
            params["positionSide"] = "BOTH"

        if reduce_only is not None:
            params["reduceOnly"] = str(reduce_only).lower()

        if close_position is not None:
            params["closePosition"] = str(close_position).lower()

        if activation_price is not None:
            params["activationPrice"] = str(activation_price)

        if callback_rate is not None:
            params["callbackRate"] = str(callback_rate)

        if working_type is not None:
            params["workingType"] = working_type.value if isinstance(working_type, WorkingType) else working_type

        if price_protect is not None:
            params["priceProtect"] = str(price_protect).lower()

        if new_client_order_id is not None:
            params["newClientOrderId"] = new_client_order_id

        response = self._post(self.ENDPOINTS["order"], params)
        return OrderResult.from_response(response)

    # ==================== Convenience Order Methods ====================

    def market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        position_side: PositionSide = PositionSide.BOTH,
        reduce_only: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a market order.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            position_side: Position side for hedge mode
            reduce_only: If True, only reduce position
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            position_side=position_side,
            reduce_only=reduce_only if reduce_only else None,
            new_client_order_id=new_client_order_id
        )

    def limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = PositionSide.BOTH,
        reduce_only: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a limit order.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price
            time_in_force: GTC, IOC, FOK, or GTX (post-only)
            position_side: Position side for hedge mode
            reduce_only: If True, only reduce position
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> order = client.limit_order("BTCUSDT", OrderSide.BUY, 0.01, 40000)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            position_side=position_side,
            reduce_only=reduce_only if reduce_only else None,
            new_client_order_id=new_client_order_id
        )

    def post_only_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        position_side: PositionSide = PositionSide.BOTH,
        reduce_only: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a post-only (maker) limit order.

        Order will be rejected if it would execute immediately as taker.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price
            position_side: Position side for hedge mode
            reduce_only: If True, only reduce position
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details
        """
        return self.limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            time_in_force=TimeInForce.GTX,
            position_side=position_side,
            reduce_only=reduce_only,
            new_client_order_id=new_client_order_id
        )

    def stop_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = False,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a stop market order.

        Triggers a market order when stop_price is reached.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            stop_price: Trigger price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> # Stop loss for long position
            >>> order = client.stop_market_order("BTCUSDT", OrderSide.SELL, 0.01, 39000)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = False,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a stop limit order.

        Triggers a limit order when stop_price is reached.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price after trigger
            stop_price: Trigger price
            time_in_force: GTC, IOC, FOK, or GTX
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def take_profit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a take profit market order.

        Triggers a market order when stop_price is reached (for profit taking).

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            stop_price: Trigger price (take profit level)
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> # Take profit for long position
            >>> order = client.take_profit_market_order("BTCUSDT", OrderSide.SELL, 0.01, 45000)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def take_profit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a take profit limit order.

        Triggers a limit order when stop_price is reached (for profit taking).

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price after trigger
            stop_price: Trigger price (take profit level)
            time_in_force: GTC, IOC, FOK, or GTX
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def trailing_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        callback_rate: float,
        activation_price: Optional[float] = None,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Place a trailing stop market order.

        Follows the price and triggers when price reverses by callback_rate%.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            callback_rate: Callback rate percentage (0.1 to 5)
            activation_price: Price at which trailing starts (optional)
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> # Trailing stop with 1% callback
            >>> order = client.trailing_stop_order("BTCUSDT", OrderSide.SELL, 0.01, 1.0)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.TRAILING_STOP_MARKET,
            quantity=quantity,
            callback_rate=callback_rate,
            activation_price=activation_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def close_position_order(
        self,
        symbol: str,
        side: OrderSide,
        position_side: PositionSide = PositionSide.BOTH,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Close entire position with a market order.

        Args:
            symbol: Trading pair symbol
            side: BUY (to close short) or SELL (to close long)
            position_side: Position side for hedge mode
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details

        Example:
            >>> # Close long position
            >>> order = client.close_position_order("BTCUSDT", OrderSide.SELL)
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            close_position=True,
            position_side=position_side,
            new_client_order_id=new_client_order_id
        )

    def stop_loss_close_position(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Set a stop loss that closes entire position when triggered.

        Args:
            symbol: Trading pair symbol
            side: BUY (for short) or SELL (for long)
            stop_price: Trigger price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET,
            stop_price=stop_price,
            close_position=True,
            position_side=position_side,
            working_type=working_type,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def take_profit_close_position(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Set a take profit that closes entire position when triggered.

        Args:
            symbol: Trading pair symbol
            side: BUY (for short) or SELL (for long)
            stop_price: Take profit price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            OrderResult with order details
        """
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            stop_price=stop_price,
            close_position=True,
            position_side=position_side,
            working_type=working_type,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    # ==================== Batch Orders ====================

    def place_batch_orders(
        self,
        orders: List[Dict[str, Any]]
    ) -> List[OrderResult]:
        """
        Place multiple orders in a single request (max 5 orders).

        Args:
            orders: List of order parameter dictionaries

        Returns:
            List of OrderResult objects

        Example:
            >>> orders = [
            ...     {"symbol": "BTCUSDT", "side": "BUY", "type": "LIMIT",
            ...      "quantity": 0.01, "price": 40000, "timeInForce": "GTC"},
            ...     {"symbol": "BTCUSDT", "side": "SELL", "type": "LIMIT",
            ...      "quantity": 0.01, "price": 45000, "timeInForce": "GTC"}
            ... ]
            >>> results = client.place_batch_orders(orders)
        """
        import json

        if len(orders) > 5:
            raise ValueError("Maximum 5 orders allowed per batch request")

        # Process orders to match API format
        processed_orders = []
        for order in orders:
            processed = {}
            for key, value in order.items():
                if isinstance(value, Enum):
                    processed[key] = value.value
                elif isinstance(value, bool):
                    processed[key] = str(value).lower()
                elif isinstance(value, (int, float)):
                    processed[key] = str(value)
                else:
                    processed[key] = value
            processed_orders.append(processed)

        params = {
            "batchOrders": json.dumps(processed_orders)
        }

        responses = self._post(self.ENDPOINTS["batch_orders"], params)
        return [OrderResult.from_response(r) for r in responses]

    def place_bracket_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        entry_price: Optional[float] = None,
        stop_loss_price: float = None,
        take_profit_price: float = None,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE
    ) -> List[OrderResult]:
        """
        Place a bracket order (entry + stop loss + take profit).

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL for entry
            quantity: Order quantity
            entry_price: Entry price (None for market entry)
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE

        Returns:
            List of OrderResult objects for all placed orders

        Example:
            >>> # Market entry with SL and TP
            >>> orders = client.place_bracket_order(
            ...     "BTCUSDT", OrderSide.BUY, 0.01,
            ...     stop_loss_price=39000, take_profit_price=45000
            ... )
        """
        results = []

        # Determine exit side (opposite of entry)
        exit_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY

        # Place entry order
        if entry_price is None:
            entry_order = self.market_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                position_side=position_side
            )
        else:
            entry_order = self.limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=entry_price,
                position_side=position_side
            )
        results.append(entry_order)

        # Place stop loss if specified
        if stop_loss_price is not None:
            sl_order = self.stop_market_order(
                symbol=symbol,
                side=exit_side,
                quantity=quantity,
                stop_price=stop_loss_price,
                position_side=position_side,
                working_type=working_type,
                reduce_only=True
            )
            results.append(sl_order)

        # Place take profit if specified
        if take_profit_price is not None:
            tp_order = self.take_profit_market_order(
                symbol=symbol,
                side=exit_side,
                quantity=quantity,
                stop_price=take_profit_price,
                position_side=position_side,
                working_type=working_type,
                reduce_only=True
            )
            results.append(tp_order)

        return results

    # ==================== Algo Orders (Conditional - Post Dec 2025) ====================
    # Since December 9, 2025, Binance migrated conditional orders to the Algo Service.
    # Order types affected: STOP_MARKET, TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT, TRAILING_STOP_MARKET
    # The old /fapi/v1/order endpoint returns error -4120 for these order types.

    def place_algo_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: AlgoOrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        position_side: PositionSide = PositionSide.BOTH,
        reduce_only: Optional[bool] = None,
        close_position: Optional[bool] = None,
        activation_price: Optional[float] = None,
        callback_rate: Optional[float] = None,
        working_type: Optional[WorkingType] = None,
        price_protect: Optional[bool] = None,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place an algo order (conditional order) via the new Algo Service API.

        IMPORTANT: Since December 9, 2025, all conditional orders must use this endpoint.
        The standard /fapi/v1/order endpoint will return error -4120 for these order types.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            order_type: Algo order type (STOP, STOP_MARKET, TAKE_PROFIT, etc.)
            quantity: Order quantity (not required if close_position=True)
            price: Limit price (required for STOP and TAKE_PROFIT)
            stop_price: Trigger price (required for all conditional orders)
            time_in_force: Time in force (GTC, IOC, FOK, GTX)
            position_side: Position side for hedge mode (BOTH, LONG, SHORT)
            reduce_only: Reduce only flag
            close_position: Close entire position when triggered
            activation_price: Activation price for trailing stop
            callback_rate: Callback rate for trailing stop (0.1 to 5)
            working_type: MARK_PRICE or CONTRACT_PRICE
            price_protect: Enable price protection
            new_client_order_id: Custom client order ID

        Returns:
            AlgoOrderResult object with order details

        Example:
            >>> # Stop loss using new Algo API
            >>> order = client.place_algo_order(
            ...     "BTCUSDT", OrderSide.SELL, AlgoOrderType.STOP_MARKET,
            ...     quantity=0.01, stop_price=39000
            ... )
        """
        params = {
            "symbol": symbol.upper(),
            "side": side.value if isinstance(side, OrderSide) else side,
            "type": order_type.value if isinstance(order_type, AlgoOrderType) else order_type,
        }

        if quantity is not None:
            params["quantity"] = str(quantity)

        if price is not None:
            params["price"] = str(price)

        if stop_price is not None:
            params["stopPrice"] = str(stop_price)

        if time_in_force is not None:
            params["timeInForce"] = time_in_force.value if isinstance(time_in_force, TimeInForce) else time_in_force

        params["positionSide"] = position_side.value if isinstance(position_side, PositionSide) else position_side

        if reduce_only is not None:
            params["reduceOnly"] = str(reduce_only).lower()

        if close_position is not None:
            params["closePosition"] = str(close_position).lower()

        if activation_price is not None:
            params["activationPrice"] = str(activation_price)

        if callback_rate is not None:
            params["callbackRate"] = str(callback_rate)

        if working_type is not None:
            params["workingType"] = working_type.value if isinstance(working_type, WorkingType) else working_type

        if price_protect is not None:
            params["priceProtect"] = str(price_protect).lower()

        if new_client_order_id is not None:
            params["newClientOrderId"] = new_client_order_id

        response = self._post(self.ENDPOINTS["algo_order"], params)
        return AlgoOrderResult.from_response(response)

    def algo_stop_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = False,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a stop market order via the Algo Service API.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            stop_price: Trigger price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details

        Example:
            >>> order = client.algo_stop_market_order("BTCUSDT", OrderSide.SELL, 0.01, 39000)
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = False,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a stop limit order via the Algo Service API.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price after trigger
            stop_price: Trigger price
            time_in_force: GTC, IOC, FOK, or GTX
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.STOP,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_take_profit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a take profit market order via the Algo Service API.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            stop_price: Trigger price (take profit level)
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details

        Example:
            >>> order = client.algo_take_profit_market_order("BTCUSDT", OrderSide.SELL, 0.01, 45000)
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.TAKE_PROFIT_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_take_profit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a take profit limit order via the Algo Service API.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price after trigger
            stop_price: Trigger price (take profit level)
            time_in_force: GTC, IOC, FOK, or GTX
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.TAKE_PROFIT,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_trailing_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        callback_rate: float,
        activation_price: Optional[float] = None,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        reduce_only: bool = True,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a trailing stop market order via the Algo Service API.

        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            quantity: Order quantity
            callback_rate: Callback rate percentage (0.1 to 5)
            activation_price: Price at which trailing starts (optional)
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            reduce_only: If True, only reduce position (default True)
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details

        Example:
            >>> order = client.algo_trailing_stop_order("BTCUSDT", OrderSide.SELL, 0.01, 1.0)
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.TRAILING_STOP_MARKET,
            quantity=quantity,
            callback_rate=callback_rate,
            activation_price=activation_price,
            position_side=position_side,
            working_type=working_type,
            reduce_only=reduce_only if reduce_only else None,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_close_position_stop_loss(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a stop loss that closes entire position when triggered (Algo API).

        Args:
            symbol: Trading pair symbol
            side: BUY (for short) or SELL (for long)
            stop_price: Trigger price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.STOP_MARKET,
            stop_price=stop_price,
            close_position=True,
            position_side=position_side,
            working_type=working_type,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def algo_close_position_take_profit(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: float,
        position_side: PositionSide = PositionSide.BOTH,
        working_type: WorkingType = WorkingType.CONTRACT_PRICE,
        price_protect: bool = False,
        new_client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Place a take profit that closes entire position when triggered (Algo API).

        Args:
            symbol: Trading pair symbol
            side: BUY (for short) or SELL (for long)
            stop_price: Take profit price
            position_side: Position side for hedge mode
            working_type: MARK_PRICE or CONTRACT_PRICE
            price_protect: Enable price protection
            new_client_order_id: Custom order ID

        Returns:
            AlgoOrderResult with order details
        """
        return self.place_algo_order(
            symbol=symbol,
            side=side,
            order_type=AlgoOrderType.TAKE_PROFIT_MARKET,
            stop_price=stop_price,
            close_position=True,
            position_side=position_side,
            working_type=working_type,
            price_protect=price_protect if price_protect else None,
            new_client_order_id=new_client_order_id
        )

    def get_algo_order(
        self,
        symbol: str,
        algo_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Query an algo order.

        Args:
            symbol: Trading pair symbol
            algo_id: Algo order ID
            client_order_id: Custom client order ID

        Returns:
            AlgoOrderResult with order details
        """
        params = {"symbol": symbol.upper()}

        if algo_id is not None:
            params["algoId"] = algo_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either algo_id or client_order_id must be provided")

        response = self._get(self.ENDPOINTS["algo_order"], params)
        return AlgoOrderResult.from_response(response)

    def cancel_algo_order(
        self,
        symbol: str,
        algo_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> AlgoOrderResult:
        """
        Cancel an algo order.

        Args:
            symbol: Trading pair symbol
            algo_id: Algo order ID
            client_order_id: Custom client order ID

        Returns:
            AlgoOrderResult with cancelled order details
        """
        params = {"symbol": symbol.upper()}

        if algo_id is not None:
            params["algoId"] = algo_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either algo_id or client_order_id must be provided")

        response = self._delete(self.ENDPOINTS["algo_order"], params)
        return AlgoOrderResult.from_response(response)

    def cancel_all_algo_orders(self, symbol: str) -> Dict[str, Any]:
        """
        Cancel all open algo orders for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            API response confirming cancellation
        """
        params = {"symbol": symbol.upper()}
        return self._delete(self.ENDPOINTS["algo_cancel_all"], params)

    def get_open_algo_orders(self, symbol: Optional[str] = None) -> List[AlgoOrderResult]:
        """
        Get all open algo orders.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of AlgoOrderResult objects
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        responses = self._get(self.ENDPOINTS["algo_open_orders"], params)
        orders = responses.get("orders", responses) if isinstance(responses, dict) else responses
        return [AlgoOrderResult.from_response(r) for r in orders]

    def get_all_algo_orders(
        self,
        symbol: str,
        algo_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[AlgoOrderResult]:
        """
        Get all algo orders (active, canceled, triggered).

        Args:
            symbol: Trading pair symbol
            algo_id: Algo order ID to start from
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            limit: Number of results (max 1000)

        Returns:
            List of AlgoOrderResult objects
        """
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000)
        }

        if algo_id is not None:
            params["algoId"] = algo_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        responses = self._get(self.ENDPOINTS["algo_all_orders"], params)
        orders = responses.get("orders", responses) if isinstance(responses, dict) else responses
        return [AlgoOrderResult.from_response(r) for r in orders]

    # ==================== TWAP Orders (Time-Weighted Average Price) ====================

    def place_twap_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        duration: int,
        position_side: PositionSide = PositionSide.BOTH,
        limit_price: Optional[float] = None,
        reduce_only: bool = False,
        client_algo_id: Optional[str] = None
    ) -> TWAPOrderResult:
        """
        Place a TWAP (Time-Weighted Average Price) order.

        TWAP executes a large order by slicing it into smaller orders over a specified duration,
        aiming to achieve an average execution price close to the time-weighted average price.

        Constraints:
        - Notional (qty * mark price) must be between 10,000 and 1,000,000 USDT
        - Duration: 300 to 86,400 seconds (5 min to 24 hours)
        - Max 10 simultaneous TWAP orders per account
        - quantity * 60 / duration should be larger than minQty

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            quantity: Total quantity to execute
            duration: Duration in seconds (300-86400)
            position_side: Position side for hedge mode
            limit_price: Optional limit price (market price if not specified)
            reduce_only: If True, only reduce position
            client_algo_id: Custom algo ID (max 32 chars)

        Returns:
            TWAPOrderResult with order details

        Note:
            Receiving success=True doesn't mean order will execute.
            Use get_twap_open_orders() or get_twap_historical_orders() to check status.

        Example:
            >>> # Execute 1 BTC over 1 hour
            >>> order = client.place_twap_order("BTCUSDT", OrderSide.BUY, 1.0, duration=3600)
        """
        if duration < 300 or duration > 86400:
            raise ValueError("Duration must be between 300 and 86400 seconds")

        params = {
            "symbol": symbol.upper(),
            "side": side.value if isinstance(side, OrderSide) else side,
            "quantity": str(quantity),
            "duration": duration,
            "positionSide": position_side.value if isinstance(position_side, PositionSide) else position_side,
        }

        if limit_price is not None:
            params["limitPrice"] = str(limit_price)

        if reduce_only:
            params["reduceOnly"] = "true"

        if client_algo_id is not None:
            params["clientAlgoId"] = client_algo_id

        response = self._sapi_post(self.ENDPOINTS["twap_new"], params)
        return TWAPOrderResult.from_response(response)

    # ==================== VP Orders (Volume Participation) ====================

    def place_vp_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        urgency: VPUrgency = VPUrgency.LOW,
        position_side: PositionSide = PositionSide.BOTH,
        limit_price: Optional[float] = None,
        reduce_only: bool = False,
        client_algo_id: Optional[str] = None
    ) -> VPOrderResult:
        """
        Place a VP (Volume Participation) order.

        VP is an opportunistic execution strategy that executes orders at a pace matching
        a portion of the real-time market volume based on the urgency level.

        Urgency levels determine participation rate:
        - LOW: Lower participation rate, minimal market impact
        - MEDIUM: Balanced participation rate
        - HIGH: Higher participation rate, faster execution

        Constraints:
        - Notional (qty * mark price) must be between 10,000 and 1,000,000 USDT
        - Max 10 simultaneous VP orders per account

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side (BUY or SELL)
            quantity: Total quantity to execute
            urgency: Urgency level (LOW, MEDIUM, HIGH)
            position_side: Position side for hedge mode
            limit_price: Optional limit price (market price if not specified)
            reduce_only: If True, only reduce position
            client_algo_id: Custom algo ID (max 32 chars)

        Returns:
            VPOrderResult with order details

        Note:
            Receiving success=True doesn't mean order will execute.
            Use get_vp_open_orders() or get_vp_historical_orders() to check status.

        Example:
            >>> # Execute 1 BTC with low market impact
            >>> order = client.place_vp_order("BTCUSDT", OrderSide.BUY, 1.0, VPUrgency.LOW)
        """
        params = {
            "symbol": symbol.upper(),
            "side": side.value if isinstance(side, OrderSide) else side,
            "quantity": str(quantity),
            "urgency": urgency.value if isinstance(urgency, VPUrgency) else urgency,
            "positionSide": position_side.value if isinstance(position_side, PositionSide) else position_side,
        }

        if limit_price is not None:
            params["limitPrice"] = str(limit_price)

        if reduce_only:
            params["reduceOnly"] = "true"

        if client_algo_id is not None:
            params["clientAlgoId"] = client_algo_id

        response = self._sapi_post(self.ENDPOINTS["vp_new"], params)
        return VPOrderResult.from_response(response)

    # ==================== TWAP/VP Order Management ====================

    def cancel_twap_vp_order(self, algo_id: int) -> Dict[str, Any]:
        """
        Cancel a TWAP or VP order.

        Args:
            algo_id: The algo order ID to cancel

        Returns:
            API response confirming cancellation
        """
        params = {"algoId": algo_id}
        return self._sapi_delete(self.ENDPOINTS["algo_cancel"], params)

    def get_twap_vp_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open TWAP and VP orders.

        Returns:
            List of open algo order dictionaries
        """
        response = self._sapi_get(self.ENDPOINTS["algo_sapi_open_orders"])
        return response.get("orders", [])

    def get_twap_vp_historical_orders(
        self,
        symbol: Optional[str] = None,
        side: Optional[OrderSide] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        page: int = 1,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """
        Get historical TWAP and VP orders.

        Args:
            symbol: Trading pair symbol (optional)
            side: Order side filter (optional)
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            page: Page number (starting from 1)
            page_size: Results per page (max 100)

        Returns:
            Dict with 'total' count and 'orders' list
        """
        params = {
            "page": page,
            "pageSize": min(page_size, 100)
        }

        if symbol is not None:
            params["symbol"] = symbol.upper()
        if side is not None:
            params["side"] = side.value if isinstance(side, OrderSide) else side
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._sapi_get(self.ENDPOINTS["algo_sapi_historical_orders"], params)

    def get_twap_vp_sub_orders(self, algo_id: int, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
        """
        Get sub-orders (child orders) of a TWAP or VP order.

        TWAP/VP orders are executed via multiple smaller sub-orders.
        This method returns the details of these sub-orders.

        Args:
            algo_id: The parent algo order ID
            page: Page number (starting from 1)
            page_size: Results per page (max 100)

        Returns:
            Dict with 'total' count and 'executedQty', 'executedAmt', 'subOrders' list
        """
        params = {
            "algoId": algo_id,
            "page": page,
            "pageSize": min(page_size, 100)
        }
        return self._sapi_get(self.ENDPOINTS["algo_sapi_sub_orders"], params)

    # ==================== Order Management ====================

    def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Query order status.

        Args:
            symbol: Trading pair symbol
            order_id: Binance order ID
            client_order_id: Custom client order ID

        Returns:
            OrderResult with order details
        """
        params = {"symbol": symbol.upper()}

        if order_id is not None:
            params["orderId"] = order_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id must be provided")

        response = self._get(self.ENDPOINTS["order"], params)
        return OrderResult.from_response(response)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None
    ) -> OrderResult:
        """
        Cancel an open order.

        Args:
            symbol: Trading pair symbol
            order_id: Binance order ID
            client_order_id: Custom client order ID

        Returns:
            OrderResult with cancelled order details
        """
        params = {"symbol": symbol.upper()}

        if order_id is not None:
            params["orderId"] = order_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id must be provided")

        response = self._delete(self.ENDPOINTS["order"], params)
        return OrderResult.from_response(response)

    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """
        Cancel all open orders for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            API response confirming cancellation
        """
        params = {"symbol": symbol.upper()}
        return self._delete(self.ENDPOINTS["cancel_all_orders"], params)

    def cancel_batch_orders(
        self,
        symbol: str,
        order_ids: Optional[List[int]] = None,
        client_order_ids: Optional[List[str]] = None
    ) -> List[OrderResult]:
        """
        Cancel multiple orders in a single request.

        Args:
            symbol: Trading pair symbol
            order_ids: List of Binance order IDs
            client_order_ids: List of custom client order IDs

        Returns:
            List of OrderResult objects for cancelled orders
        """
        import json

        params = {"symbol": symbol.upper()}

        if order_ids is not None:
            params["orderIdList"] = json.dumps(order_ids)
        elif client_order_ids is not None:
            params["origClientOrderIdList"] = json.dumps(client_order_ids)
        else:
            raise ValueError("Either order_ids or client_order_ids must be provided")

        responses = self._delete(self.ENDPOINTS["batch_orders"], params)
        return [OrderResult.from_response(r) for r in responses]

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """
        Get all open orders.

        Args:
            symbol: Trading pair symbol (optional, returns all if not specified)

        Returns:
            List of OrderResult objects for open orders
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        responses = self._get(self.ENDPOINTS["all_open_orders"], params)
        return [OrderResult.from_response(r) for r in responses]

    def get_all_orders(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[OrderResult]:
        """
        Get all orders (active, canceled, filled).

        Args:
            symbol: Trading pair symbol
            order_id: Order ID to start from
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            limit: Number of results (max 1000)

        Returns:
            List of OrderResult objects
        """
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000)
        }

        if order_id is not None:
            params["orderId"] = order_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        responses = self._get(self.ENDPOINTS["all_orders"], params)
        return [OrderResult.from_response(r) for r in responses]

    # ==================== Position Management ====================

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for a symbol.

        Args:
            symbol: Trading pair symbol
            leverage: Leverage value (1-125 depending on symbol)

        Returns:
            API response with leverage and max notional

        Example:
            >>> client.set_leverage("BTCUSDT", 20)
        """
        params = {
            "symbol": symbol.upper(),
            "leverage": leverage
        }
        return self._post(self.ENDPOINTS["leverage"], params)

    def set_margin_type(self, symbol: str, margin_type: MarginType) -> Dict[str, Any]:
        """
        Set margin type (isolated or cross).

        Args:
            symbol: Trading pair symbol
            margin_type: ISOLATED or CROSSED

        Returns:
            API response confirming change

        Example:
            >>> client.set_margin_type("BTCUSDT", MarginType.ISOLATED)
        """
        params = {
            "symbol": symbol.upper(),
            "marginType": margin_type.value if isinstance(margin_type, MarginType) else margin_type
        }
        return self._post(self.ENDPOINTS["margin_type"], params)

    def set_position_mode(self, hedge_mode: bool) -> Dict[str, Any]:
        """
        Set position mode (one-way or hedge mode).

        Args:
            hedge_mode: True for hedge mode, False for one-way mode

        Returns:
            API response confirming change

        Note:
            Hedge mode allows simultaneous long and short positions.
            One-way mode only allows one position direction at a time.
        """
        params = {
            "dualSidePosition": str(hedge_mode).lower()
        }
        return self._post(self.ENDPOINTS["position_mode"], params)

    def get_position_mode(self) -> Dict[str, Any]:
        """
        Get current position mode.

        Returns:
            Dict with dualSidePosition (True = hedge mode)
        """
        return self._get(self.ENDPOINTS["position_mode"])

    def adjust_position_margin(
        self,
        symbol: str,
        amount: float,
        add_margin: bool = True,
        position_side: PositionSide = PositionSide.BOTH
    ) -> Dict[str, Any]:
        """
        Add or remove margin from isolated position.

        Args:
            symbol: Trading pair symbol
            amount: Margin amount
            add_margin: True to add, False to remove
            position_side: Position side for hedge mode

        Returns:
            API response with updated margin info
        """
        params = {
            "symbol": symbol.upper(),
            "amount": str(amount),
            "type": 1 if add_margin else 2,
            "positionSide": position_side.value if isinstance(position_side, PositionSide) else position_side
        }
        return self._post(self.ENDPOINTS["position_margin"], params)

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get current position information.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of position information dictionaries
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        return self._get(self.ENDPOINTS["position_risk"], params)

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Get all positions with non-zero amounts.

        Returns:
            List of open position information
        """
        positions = self.get_positions()
        return [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    # ==================== Account Information ====================

    def get_account(self) -> Dict[str, Any]:
        """
        Get account information.

        Returns:
            Dict with account details including:
            - totalWalletBalance
            - totalUnrealizedProfit
            - totalMarginBalance
            - availableBalance
            - positions
            - assets
        """
        return self._get(self.ENDPOINTS["account"])

    def get_balance(self) -> List[Dict[str, Any]]:
        """
        Get account balance for all assets.

        Returns:
            List of balance information for each asset
        """
        return self._get(self.ENDPOINTS["balance"])

    def get_asset_balance(self, asset: str = "USDT") -> Dict[str, Any]:
        """
        Get balance for a specific asset.

        Args:
            asset: Asset name (default: USDT)

        Returns:
            Balance information for the asset
        """
        balances = self.get_balance()
        for balance in balances:
            if balance.get("asset") == asset.upper():
                return balance
        return {}

    def get_income_history(
        self,
        symbol: Optional[str] = None,
        income_type: Optional[IncomeType] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get income history (PnL, funding, commissions, etc.)

        Args:
            symbol: Trading pair symbol (optional)
            income_type: Type of income to filter
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            limit: Number of results (max 1000)

        Returns:
            List of income records
        """
        params = {"limit": min(limit, 1000)}

        if symbol is not None:
            params["symbol"] = symbol.upper()
        if income_type is not None:
            params["incomeType"] = income_type.value if isinstance(income_type, IncomeType) else income_type
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get(self.ENDPOINTS["income"], params)

    def get_leverage_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get leverage brackets and notional limits.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            List of leverage bracket information
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        return self._get(self.ENDPOINTS["leverage_bracket"], params)

    # ==================== Market Data ====================

    def get_exchange_info(self) -> Dict[str, Any]:
        """
        Get exchange trading rules and symbol information.

        Returns:
            Exchange information including all trading pairs and rules
        """
        return self._get(self.ENDPOINTS["exchange_info"], signed=False)

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get trading rules for a specific symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Symbol information or None if not found
        """
        exchange_info = self.get_exchange_info()
        for s in exchange_info.get("symbols", []):
            if s.get("symbol") == symbol.upper():
                return s
        return None

    def get_ticker_price(self, symbol: Optional[str] = None) -> Any:
        """
        Get current price for symbol(s).

        Args:
            symbol: Trading pair symbol (optional, returns all if not specified)

        Returns:
            Price information (single dict or list)
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        return self._get(self.ENDPOINTS["ticker_price"], params, signed=False)

    def get_ticker_24hr(self, symbol: Optional[str] = None) -> Any:
        """
        Get 24-hour price change statistics.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            24hr ticker statistics (single dict or list)
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        return self._get(self.ENDPOINTS["ticker_24hr"], params, signed=False)

    def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get order book depth.

        Args:
            symbol: Trading pair symbol
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000)

        Returns:
            Order book with bids and asks
        """
        params = {
            "symbol": symbol.upper(),
            "limit": limit
        }
        return self._get(self.ENDPOINTS["depth"], params, signed=False)

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[List]:
        """
        Get candlestick/kline data.

        Args:
            symbol: Trading pair symbol
            interval: Kline interval (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            limit: Number of candles (max 1500)

        Returns:
            List of klines [open_time, open, high, low, close, volume, close_time, ...]
        """
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1500)
        }

        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get(self.ENDPOINTS["klines"], params, signed=False)

    def get_mark_price(self, symbol: Optional[str] = None) -> Any:
        """
        Get mark price and funding rate.

        Args:
            symbol: Trading pair symbol (optional)

        Returns:
            Mark price information (single dict or list)
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()

        return self._get(self.ENDPOINTS["mark_price"], params, signed=False)

    def get_funding_rate_history(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get funding rate history.

        Args:
            symbol: Trading pair symbol
            start_time: Start timestamp in ms
            end_time: End timestamp in ms
            limit: Number of results (max 1000)

        Returns:
            List of funding rate records
        """
        params = {
            "symbol": symbol.upper(),
            "limit": min(limit, 1000)
        }

        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get(self.ENDPOINTS["funding_rate"], params, signed=False)

    # ==================== User Data Stream ====================

    def create_listen_key(self) -> str:
        """
        Create a listen key for user data stream.

        Returns:
            Listen key string for WebSocket connection
        """
        response = self._post(self.ENDPOINTS["listen_key"])
        return response.get("listenKey", "")

    def keepalive_listen_key(self) -> Dict[str, Any]:
        """
        Keep alive a user data stream.

        Returns:
            Empty dict on success
        """
        return self._put(self.ENDPOINTS["listen_key"])

    def close_listen_key(self) -> Dict[str, Any]:
        """
        Close a user data stream.

        Returns:
            Empty dict on success
        """
        return self._delete(self.ENDPOINTS["listen_key"])

    # ==================== Utility Methods ====================

    def get_precision(self, symbol: str) -> Dict[str, int]:
        """
        Get price and quantity precision for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            Dict with price_precision and quantity_precision
        """
        info = self.get_symbol_info(symbol)
        if info is None:
            raise ValueError(f"Symbol {symbol} not found")

        return {
            "price_precision": info.get("pricePrecision", 2),
            "quantity_precision": info.get("quantityPrecision", 3)
        }

    def round_price(self, symbol: str, price: float) -> float:
        """
        Round price to correct precision for a symbol.

        Args:
            symbol: Trading pair symbol
            price: Price to round

        Returns:
            Rounded price
        """
        precision = self.get_precision(symbol)
        return round(price, precision["price_precision"])

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """
        Round quantity to correct precision for a symbol.

        Args:
            symbol: Trading pair symbol
            quantity: Quantity to round

        Returns:
            Rounded quantity
        """
        precision = self.get_precision(symbol)
        return round(quantity, precision["quantity_precision"])

    def calculate_position_size(
        self,
        symbol: str,
        risk_amount: float,
        entry_price: float,
        stop_loss_price: float
    ) -> float:
        """
        Calculate position size based on risk amount.

        Args:
            symbol: Trading pair symbol
            risk_amount: Amount willing to risk (in quote currency)
            entry_price: Planned entry price
            stop_loss_price: Planned stop loss price

        Returns:
            Position size rounded to correct precision
        """
        price_diff = abs(entry_price - stop_loss_price)
        if price_diff == 0:
            raise ValueError("Entry and stop loss prices cannot be the same")

        position_size = risk_amount / price_diff
        return self.round_quantity(symbol, position_size)


# ==================== Example Usage ====================

if __name__ == "__main__":
    # Example usage (requires valid API keys)

    # Initialize client (use testnet for testing)
    # client = BinanceFuturesClient(
    #     api_key="your_api_key",
    #     api_secret="your_api_secret",
    #     testnet=True  # Use testnet for testing
    # )

    # Example order operations:

    # 1. Market Orders
    # order = client.market_order("BTCUSDT", OrderSide.BUY, quantity=0.01)
    # order = client.market_order("BTCUSDT", OrderSide.SELL, quantity=0.01)

    # 2. Limit Orders
    # order = client.limit_order("BTCUSDT", OrderSide.BUY, 0.01, price=40000)
    # order = client.post_only_order("BTCUSDT", OrderSide.BUY, 0.01, price=40000)

    # 3. Stop Orders
    # order = client.stop_market_order("BTCUSDT", OrderSide.SELL, 0.01, stop_price=39000)
    # order = client.stop_limit_order("BTCUSDT", OrderSide.SELL, 0.01, price=38900, stop_price=39000)

    # 4. Take Profit Orders
    # order = client.take_profit_market_order("BTCUSDT", OrderSide.SELL, 0.01, stop_price=45000)
    # order = client.take_profit_limit_order("BTCUSDT", OrderSide.SELL, 0.01, price=45100, stop_price=45000)

    # 5. Trailing Stop
    # order = client.trailing_stop_order("BTCUSDT", OrderSide.SELL, 0.01, callback_rate=1.0)

    # 6. Close Position
    # order = client.close_position_order("BTCUSDT", OrderSide.SELL)

    # 7. Bracket Order (Entry + SL + TP)
    # orders = client.place_bracket_order(
    #     "BTCUSDT", OrderSide.BUY, 0.01,
    #     stop_loss_price=39000, take_profit_price=45000
    # )

    # 8. Position Management
    # client.set_leverage("BTCUSDT", 20)
    # client.set_margin_type("BTCUSDT", MarginType.ISOLATED)
    # positions = client.get_open_positions()

    # 9. Account Info
    # account = client.get_account()
    # balance = client.get_asset_balance("USDT")

    # ==================== NEW ALGO ORDERS (Post Dec 2025) ====================
    # Since Dec 9, 2025, conditional orders use the new Algo API

    # 10. Algo Stop Orders (use these instead of stop_market_order/stop_limit_order)
    # order = client.algo_stop_market_order("BTCUSDT", OrderSide.SELL, 0.01, stop_price=39000)
    # order = client.algo_stop_limit_order("BTCUSDT", OrderSide.SELL, 0.01, price=38900, stop_price=39000)

    # 11. Algo Take Profit Orders
    # order = client.algo_take_profit_market_order("BTCUSDT", OrderSide.SELL, 0.01, stop_price=45000)
    # order = client.algo_take_profit_limit_order("BTCUSDT", OrderSide.SELL, 0.01, price=45100, stop_price=45000)

    # 12. Algo Trailing Stop
    # order = client.algo_trailing_stop_order("BTCUSDT", OrderSide.SELL, 0.01, callback_rate=1.0)

    # 13. Algo Close Position Orders
    # order = client.algo_close_position_stop_loss("BTCUSDT", OrderSide.SELL, stop_price=39000)
    # order = client.algo_close_position_take_profit("BTCUSDT", OrderSide.SELL, stop_price=45000)

    # 14. Query and Cancel Algo Orders
    # open_algos = client.get_open_algo_orders("BTCUSDT")
    # client.cancel_algo_order("BTCUSDT", algo_id=123456)
    # client.cancel_all_algo_orders("BTCUSDT")

    # ==================== TWAP & VP ORDERS ====================

    # 15. TWAP Order (Time-Weighted Average Price)
    # Execute 1 BTC over 1 hour with minimal market impact
    # order = client.place_twap_order(
    #     "BTCUSDT", OrderSide.BUY, quantity=1.0,
    #     duration=3600  # 1 hour in seconds
    # )

    # 16. VP Order (Volume Participation)
    # Execute order matching market volume with specified urgency
    # order = client.place_vp_order(
    #     "BTCUSDT", OrderSide.BUY, quantity=1.0,
    #     urgency=VPUrgency.LOW  # LOW, MEDIUM, or HIGH
    # )

    # 17. Manage TWAP/VP Orders
    # open_orders = client.get_twap_vp_open_orders()
    # history = client.get_twap_vp_historical_orders(symbol="BTCUSDT")
    # sub_orders = client.get_twap_vp_sub_orders(algo_id=123456)
    # client.cancel_twap_vp_order(algo_id=123456)

    print("Binance Futures Client loaded successfully!")
    print("Initialize with: client = BinanceFuturesClient(api_key, api_secret)")
    print("\nIMPORTANT: Since Dec 9, 2025, use algo_* methods for conditional orders!")
