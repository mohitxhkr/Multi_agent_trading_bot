"""
Delta Exchange API Client with HMAC-SHA256 Authentication.
Supports Delta Exchange India, Global, and Testnet environments.
Provides high-level trading, market data, and portfolio methods.
"""

import time
import hmac
import hashlib
import json
import os
import urllib.parse
from typing import Dict, List, Any, Optional, Union
import requests
# pyrefly: ignore[missing-import]
from dotenv import load_dotenv

load_dotenv()


class DeltaExchangeClient:
    """
    Authenticated client for Delta Exchange REST API v2.
    """

    ENV_URLS = {
        "india": "https://api.india.delta.exchange",
        "global": "https://api.delta.exchange",
        "testnet": "https://testnet-api.delta.exchange",
        "testnet_india": "https://cdn-ind.testnet.deltaex.org",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        environment: str = "india",
        base_url: Optional[str] = None,
        timeout: int = 15,
    ):
        # Fallback to Delta Exchange testnet India demo credentials if unset
        default_key = "REDACTED_DELTA_API_KEY"
        default_secret = "REDACTED_DELTA_API_SECRET"

        self.api_key = (api_key or os.getenv("DELTA_API_KEY") or default_key).strip()
        self.api_secret = (api_secret or os.getenv("DELTA_API_SECRET") or default_secret).strip()
        self.environment = (os.getenv("DELTA_ENVIRONMENT") or environment).lower()
        
        if base_url:
            self.base_url = base_url.rstrip("/")
        else:
            custom_url = os.getenv("DELTA_BASE_URL")
            if custom_url:
                self.base_url = custom_url.rstrip("/")
            else:
                self.base_url = self.ENV_URLS.get(self.environment, self.ENV_URLS["india"])

        self.timeout = timeout
        self.session = requests.Session()
        self._products_cache: Dict[str, Dict[str, Any]] = {}
        self._product_id_map: Dict[str, int] = {}
        self._cache_timestamp = 0

    def _generate_signature(self, method: str, timestamp: str, path: str, query_string: str, body: str) -> str:
        """
        Construct signature payload: Method + Timestamp + Path + QueryString + Body
        and hash with HMAC-SHA256 hex digest.
        """
        signature_data = f"{method}{timestamp}{path}{query_string}{body}"
        secret_bytes = self.api_secret.encode("utf-8")
        message_bytes = signature_data.encode("utf-8")
        return hmac.new(secret_bytes, message_bytes, hashlib.sha256).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute signed HTTP request to Delta Exchange API.
        """
        method = method.upper()
        
        # Build query string
        query_string = ""
        if params:
            # Clean None values and encode
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                query_string = "?" + urllib.parse.urlencode(clean_params)

        endpoint_url = f"{self.base_url}{path}{query_string}"
        
        # Build payload body string
        body = ""
        if payload is not None:
            # Ensure separators match wire formatting without extra whitespace
            body = json.dumps(payload, separators=(",", ":"))

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Delta-Exchange-MCP-Client/1.0"
        }

        if authenticated:
            if not self.api_key or not self.api_secret:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_API_CREDENTIALS",
                        "message": "Delta Exchange API Key and API Secret must be set in .env or passed to client."
                    }
                }
            timestamp = str(int(time.time()))
            signature = self._generate_signature(method, timestamp, path, query_string, body)
            headers["api-key"] = self.api_key
            headers["timestamp"] = timestamp
            headers["signature"] = signature

        for attempt in range(2):
            try:
                response = self.session.request(
                    method=method,
                    url=endpoint_url,
                    headers=headers,
                    data=body if (method in ["POST", "PUT", "DELETE"] and body) else None,
                    timeout=self.timeout
                )

                if response.status_code == 429 and attempt == 0:
                    time.sleep(1.5)
                    continue

                try:
                    data = response.json()
                except ValueError:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": {"code": "INVALID_JSON", "message": response.text}
                    }

                if response.status_code >= 400:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": data.get("error", data)
                    }

                return data

            except requests.exceptions.RequestException as e:
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                return {
                    "success": False,
                    "error": {
                        "code": "NETWORK_ERROR",
                        "message": str(e)
                    }
                }

    # -------------------------------------------------------------------------
    # Product Discovery & Cache
    # -------------------------------------------------------------------------
    def load_products(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """Fetch and cache all tradable products from Delta Exchange."""
        now = time.time()
        if not force_refresh and self._products_cache and (now - self._cache_timestamp < 3600):
            return self._products_cache

        res = self._request("GET", "/v2/products", authenticated=False)
        if res.get("success") and "result" in res:
            self._products_cache = {}
            self._product_id_map = {}
            for item in res["result"]:
                symbol = item.get("symbol")
                pid = item.get("id")
                if symbol and pid:
                    self._products_cache[symbol] = item
                    self._product_id_map[symbol] = pid
            self._cache_timestamp = now
            
        return self._products_cache

    def resolve_symbol(self, symbol: str) -> str:
        """
        Automatically resolve symbols between Delta India (e.g. BTCUSD) and Delta Global (e.g. BTCUSDT).
        Also maps commodity & gold aliases such as XAUUSD / GOLD -> XAUTUSD / PAXGUSD.
        """
        sym = symbol.strip().upper()
        self.load_products()

        # Handle Gold / Commodity aliases
        if sym in ["XAUUSD", "GOLD", "GOLDUSD", "XAU"]:
            if "XAUTUSD" in self._products_cache:
                return "XAUTUSD"
            if "PAXGUSD" in self._products_cache:
                return "PAXGUSD"

        if sym in self._products_cache:
            return sym
        if sym.endswith("USDT") and sym[:-1] in self._products_cache:
            return sym[:-1]
        if sym.endswith("USD") and (sym + "T") in self._products_cache:
            return sym + "T"
        return sym

    def get_product_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get product metadata by symbol (e.g. 'BTCUSDT' or 'BTCUSD')."""
        resolved = self.resolve_symbol(symbol)
        return self._products_cache.get(resolved)

    def get_product_id(self, symbol: str) -> Optional[int]:
        """Convert symbol to product_id integer."""
        resolved = self.resolve_symbol(symbol)
        return self._product_id_map.get(resolved)

    def get_tick_size(self, symbol: str) -> float:
        """Get product minimum price tick size as float."""
        pinfo = self.get_product_info(symbol)
        if pinfo and pinfo.get("tick_size"):
            try:
                return float(pinfo["tick_size"])
            except (ValueError, TypeError):
                pass
        return 0.01

    def round_to_tick(self, symbol: str, price: float) -> float:
        """
        Round price strictly to the contract's tick size increments.
        Guarantees orders are not rejected by Delta Exchange for tick size invalidity.
        """
        tick = self.get_tick_size(symbol)
        if tick <= 0:
            return round(price, 2)

        tick_str = f"{tick:.8f}".rstrip("0")
        if "." in tick_str:
            decimals = len(tick_str.split(".")[1])
        else:
            decimals = 0

        steps = round(price / tick)
        rounded = steps * tick
        return round(rounded, decimals)

    # -------------------------------------------------------------------------
    # Diagnostics & Connectivity
    # -------------------------------------------------------------------------
    def test_connection(self) -> Dict[str, Any]:
        """Check public connection and API credentials validity."""
        public_res = self._request("GET", "/v2/products", authenticated=False)
        public_ok = public_res.get("success", False)
        
        auth_ok = False
        auth_msg = ""
        account_data = None
        
        if self.api_key and self.api_secret:
            auth_res = self._request("GET", "/v2/wallet/balances", authenticated=True)
            if auth_res.get("success"):
                auth_ok = True
                auth_msg = "Authenticated successfully with Delta Exchange."
                account_data = auth_res.get("result")
            else:
                auth_msg = str(auth_res.get("error", "Authentication failed"))
        else:
            auth_msg = "API credentials not configured yet."

        return {
            "environment": self.environment,
            "base_url": self.base_url,
            "public_api_connected": public_ok,
            "authenticated": auth_ok,
            "message": auth_msg,
            "account_balances": account_data
        }

    # -------------------------------------------------------------------------
    # Account & Portfolio Endpoints
    # -------------------------------------------------------------------------
    def get_wallet_balances(self) -> Dict[str, Any]:
        """Get account wallet balances across assets (USDT, BTC, etc.)."""
        return self._request("GET", "/v2/wallet/balances", authenticated=True)

    def get_positions(self) -> Dict[str, Any]:
        """Get all active margined futures and options positions."""
        return self._request("GET", "/v2/positions/margined", authenticated=True)

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get open/pending orders."""
        params = {"state": "open"}
        if symbol:
            pid = self.get_product_id(symbol)
            if pid:
                params["product_id"] = pid
        return self._request("GET", "/v2/orders", params=params, authenticated=True)

    def get_order_history(self, symbol: Optional[str] = None, page_size: int = 20) -> Dict[str, Any]:
        """Get order execution history."""
        params = {"page_size": page_size}
        if symbol:
            pid = self.get_product_id(symbol)
            if pid:
                params["product_id"] = pid
        return self._request("GET", "/v2/orders/history", params=params, authenticated=True)

    def get_fills(self, symbol: Optional[str] = None, page_size: int = 20) -> Dict[str, Any]:
        """Get recent trade fills."""
        params = {"page_size": page_size}
        if symbol:
            pid = self.get_product_id(symbol)
            if pid:
                params["product_id"] = pid
        return self._request("GET", "/v2/fills", params=params, authenticated=True)

    # -------------------------------------------------------------------------
    # Market Data Endpoints
    # -------------------------------------------------------------------------
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get real-time ticker data (mark price, 24h stats, funding rate)."""
        resolved = self.resolve_symbol(symbol)
        return self._request("GET", f"/v2/tickers/{resolved}", authenticated=False)

    def get_all_tickers(self) -> Dict[str, Any]:
        """Get tickers for all live contracts."""
        return self._request("GET", "/v2/tickers", authenticated=False)

    def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Get Level 2 orderbook for symbol."""
        resolved = self.resolve_symbol(symbol)
        return self._request("GET", f"/v2/l2orderbook/{resolved}", authenticated=False)

    def get_candles(
        self,
        symbol: str,
        resolution: str = "60",
        from_time: Optional[int] = None,
        to_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get OHLCV candlestick data.
        Allowed resolutions: 1, 3, 5, 15, 30, 60, 120, 240, 360, D, W
        """
        resolved = self.resolve_symbol(symbol)
        now = int(time.time())
        end = to_time if to_time is not None else now
        # Default lookback 100 periods
        res_seconds_map = {
            "1": 60, "3": 180, "5": 300, "15": 900, "30": 1800,
            "60": 3600, "120": 7200, "240": 14400, "360": 21600,
            "D": 86400, "W": 604800
        }
        step_sec = res_seconds_map.get(str(resolution), 3600)
        start = from_time if from_time is not None else (end - (step_sec * 100))

        params = {
            "symbol": resolved,
            "resolution": resolution,
            "from": start,
            "to": end
        }
        return self._request("GET", "/v2/chart/history", params=params, authenticated=False)

    def get_options_chain(self, underlying_asset: str = "BTC") -> Dict[str, Any]:
        """
        Get options contracts with Greeks (Delta, Gamma, Vega, Theta) and IV.
        """
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": underlying_asset.upper()
        }
        return self._request("GET", "/v2/tickers", params=params, authenticated=False)

    # -------------------------------------------------------------------------
    # Trading & Execution Endpoints
    # -------------------------------------------------------------------------
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a contract product (e.g. 5 for 5x)."""
        pid = self.get_product_id(symbol)
        if not pid:
            return {"success": False, "error": f"Symbol {symbol} not found in product cache"}

        payload = {"leverage": str(leverage)}
        return self._request("POST", f"/v2/products/{pid}/orders/leverage", payload=payload, authenticated=True)

    def place_order(
        self,
        symbol: str,
        size: int,
        side: str,
        order_type: str = "limit_order",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "gtc",
        post_only: bool = False,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Place standard order on Delta Exchange.
        order_type: 'market_order', 'limit_order', 'stop_market_order', 'stop_limit_order'
        side: 'buy' or 'sell'
        size: number of contracts (integer)
        """
        pid = self.get_product_id(symbol)
        if not pid:
            return {"success": False, "error": f"Product not found for symbol {symbol}"}

        payload: Dict[str, Any] = {
            "product_id": pid,
            "size": int(size),
            "side": side.lower(),
            "order_type": order_type.lower(),
            "time_in_force": time_in_force.lower(),
            "post_only": post_only,
            "reduce_only": reduce_only
        }

        if limit_price is not None:
            payload["limit_price"] = str(limit_price)

        if stop_price is not None:
            payload["stop_price"] = str(stop_price)

        return self._request("POST", "/v2/orders", payload=payload, authenticated=True)

    def place_bracket_order(
        self,
        symbol: str,
        size: int,
        side: str,
        order_type: str = "limit_order",
        limit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place order with attached protective bracket Stop-Loss and Take-Profit.
        """
        pid = self.get_product_id(symbol)
        if not pid:
            return {"success": False, "error": f"Product not found for symbol {symbol}"}

        payload: Dict[str, Any] = {
            "product_id": pid,
            "size": int(size),
            "side": side.lower(),
            "order_type": order_type.lower(),
            "time_in_force": "gtc"
        }

        if limit_price is not None:
            payload["limit_price"] = str(limit_price)

        if stop_loss_price is not None:
            payload["bracket_stop_loss_price"] = str(stop_loss_price)
            payload["bracket_stop_loss_limit_price"] = str(stop_loss_price)

        if take_profit_price is not None:
            payload["bracket_take_profit_price"] = str(take_profit_price)
            payload["bracket_take_profit_limit_price"] = str(take_profit_price)

        return self._request("POST", "/v2/orders", payload=payload, authenticated=True)

    def edit_order(
        self,
        order_id: int,
        product_id: Optional[int] = None,
        symbol: Optional[str] = None,
        stop_price: Optional[float] = None,
        limit_price: Optional[float] = None,
        size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Edit an open order or bracket order on Delta Exchange.
        Endpoint: PUT /v2/orders
        """
        pid = product_id
        if pid is None and symbol:
            pid = self.get_product_id(symbol)

        if not pid:
            return {"success": False, "error": "product_id or valid symbol is required"}

        payload: Dict[str, Any] = {
            "id": int(order_id),
            "product_id": int(pid),
        }
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if size is not None:
            payload["size"] = int(size)

        return self._request("PUT", "/v2/orders", payload=payload, authenticated=True)

    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an open order by ID."""
        pid = self.get_product_id(symbol)
        if not pid:
            return {"success": False, "error": f"Product not found for symbol {symbol}"}

        payload = {
            "id": int(order_id),
            "product_id": pid
        }
        return self._request("DELETE", "/v2/orders", payload=payload, authenticated=True)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Cancel all open orders, optionally filtered by symbol."""
        payload: Dict[str, Any] = {}
        if symbol:
            pid = self.get_product_id(symbol)
            if pid:
                payload["product_id"] = pid
        return self._request("DELETE", "/v2/orders/all", payload=payload, authenticated=True)

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close an active position using market order."""
        pid = self.get_product_id(symbol)
        if not pid:
            return {"success": False, "error": f"Product not found for symbol {symbol}"}

        payload = {"product_id": pid}
        return self._request("POST", "/v2/positions/close", payload=payload, authenticated=True)
