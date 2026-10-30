"""
Delta Exchange Model Context Protocol (MCP) Server.
Exposes rich trading, market data, risk management, and journal tools to Claude.
Supports both official FastMCP (mcp package) and lightweight standard JSON-RPC 2.0 stdio fallback.
"""

import sys
import os
import json
import logging
from typing import Dict, Any, Optional, List

# Ensure parent path is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_client import DeltaExchangeClient
from src.technical_analysis import analyze_market_structure
from src.risk_manager import RiskManager
from src.journal import (
    record_trade_entry,
    record_trade_exit,
    get_performance_summary
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("delta-mcp-server")

# Instantiate core engines
delta_client = DeltaExchangeClient()
risk_manager = RiskManager()


# =============================================================================
# Tool Implementation Functions
# =============================================================================

def tool_test_connection() -> Dict[str, Any]:
    """Test connection to Delta Exchange and verify API key/secret authentication."""
    return delta_client.test_connection()


def tool_get_account_summary() -> Dict[str, Any]:
    """Get account wallet balances across assets (USDT, BTC), total equity, and margin usage."""
    balances_res = delta_client.get_wallet_balances()
    if not balances_res.get("success"):
        return {"error": balances_res.get("error", "Failed to retrieve wallet balances")}

    balances = balances_res.get("result", [])
    positions_res = delta_client.get_positions()
    positions = positions_res.get("result", []) if positions_res.get("success") else []

    total_usdt_balance = 0.0
    available_usdt = 0.0
    for b in balances:
        symbol = b.get("asset_symbol", "")
        if symbol in ("USDT", "USD"):
            bal = float(b.get("balance", 0.0))
            avail = float(b.get("available_balance", 0.0))
            if bal > total_usdt_balance:
                total_usdt_balance = bal
                available_usdt = avail

    if total_usdt_balance <= 0:
        meta = balances_res.get("meta", {})
        net_eq = float(meta.get("net_equity", 0.0) or 0.0)
        if net_eq > 0:
            total_usdt_balance = net_eq
            available_usdt = net_eq

    return {
        "success": True,
        "environment": delta_client.environment,
        "base_url": delta_client.base_url,
        "usdt_total_balance": total_usdt_balance,
        "usdt_available_balance": available_usdt,
        "active_positions_count": len(positions),
        "raw_balances": balances
    }


def tool_get_positions() -> Dict[str, Any]:
    """Get all active margined futures and options positions with unrealized PnL, leverage, and liquidation price."""
    pos_res = delta_client.get_positions()
    if not pos_res.get("success"):
        return {"error": pos_res.get("error", "Failed to retrieve positions")}

    raw_positions = pos_res.get("result", [])
    active_positions = []
    
    for p in raw_positions:
        size = float(p.get("size", 0))
        if size != 0:
            active_positions.append({
                "symbol": p.get("product_symbol"),
                "product_id": p.get("product_id"),
                "size": size,
                "side": "LONG" if size > 0 else "SHORT",
                "entry_price": float(p.get("entry_price", 0.0)),
                "liquidation_price": float(p.get("liquidation_price", 0.0)),
                "unrealized_pnl": float(p.get("unrealized_pnl", 0.0)),
                "realized_pnl": float(p.get("realized_pnl", 0.0)),
                "leverage": p.get("leverage"),
                "margin": float(p.get("margin", 0.0))
            })

    return {
        "success": True,
        "total_active_positions": len(active_positions),
        "positions": active_positions
    }


def tool_get_open_orders(symbol: Optional[str] = None) -> Dict[str, Any]:
    """List all open/pending orders on the orderbook with limit price, trigger price, and side."""
    orders_res = delta_client.get_open_orders(symbol=symbol)
    if not orders_res.get("success"):
        return {"error": orders_res.get("error", "Failed to retrieve open orders")}

    orders = orders_res.get("result", [])
    clean_orders = []
    for o in orders:
        clean_orders.append({
            "order_id": o.get("id"),
            "product_id": o.get("product_id"),
            "symbol": o.get("product_symbol"),
            "side": o.get("side"),
            "order_type": o.get("order_type"),
            "size": o.get("size"),
            "unfilled_size": o.get("unfilled_size"),
            "limit_price": o.get("limit_price"),
            "stop_price": o.get("stop_price"),
            "state": o.get("state"),
            "created_at": o.get("created_at")
        })

    return {
        "success": True,
        "open_orders_count": len(clean_orders),
        "orders": clean_orders
    }


def tool_get_order_history(symbol: Optional[str] = None, page_size: int = 20) -> Dict[str, Any]:
    """Get history of filled and cancelled orders."""
    res = delta_client.get_order_history(symbol=symbol, page_size=page_size)
    if not res.get("success"):
        return {"error": res.get("error", "Failed to retrieve order history")}
    return {"success": True, "history": res.get("result", [])}


def tool_get_ticker(symbol: str) -> Dict[str, Any]:
    """Get real-time market ticker data (mark price, close, 24h high/low, turnover, open interest)."""
    res = delta_client.get_ticker(symbol)
    if not res.get("success"):
        return {"error": res.get("error", f"Failed to get ticker for {symbol}")}
    return {"success": True, "ticker": res.get("result")}


def tool_get_orderbook(symbol: str) -> Dict[str, Any]:
    """Get Level 2 orderbook depth for a symbol (top 10 bids and asks)."""
    res = delta_client.get_orderbook(symbol)
    if not res.get("success"):
        return {"error": res.get("error", f"Failed to get orderbook for {symbol}")}

    data = res.get("result", {})
    bids = data.get("buy", [])[:10]
    asks = data.get("sell", [])[:10]

    best_bid = float(bids[0]["price"]) if bids else 0.0
    best_ask = float(asks[0]["price"]) if asks else 0.0
    spread = round(best_ask - best_bid, 4) if (best_bid and best_ask) else 0.0

    return {
        "success": True,
        "symbol": symbol.upper(),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "top_bids": bids,
        "top_asks": asks
    }


def tool_get_candles_analysis(
    symbol: str,
    resolution: str = "60",
    lookback_candles: int = 100
) -> Dict[str, Any]:
    """
    Fetch OHLCV candles from Delta Exchange and compute technical indicators
    (EMA 9/21/50/200, RSI 14, ATR 14, MACD, Support/Resistance, and Market Regime).
    """
    res = delta_client.get_candles(symbol, resolution=resolution)
    if not res.get("success"):
        return {"error": res.get("error", f"Failed to get candles for {symbol}")}

    raw_result = res.get("result", {})
    if not isinstance(raw_result, dict) or "c" not in raw_result:
        return {"error": "Invalid candlestick payload format received"}

    analysis = analyze_market_structure(raw_result)
    analysis["symbol"] = symbol.upper()
    analysis["resolution"] = resolution
    return {"success": True, "analysis": analysis}


def tool_get_options_chain(underlying_asset: str = "BTC") -> Dict[str, Any]:
    """Get options strikes, Greeks (Delta, Gamma, Vega, Theta), Implied Volatility, and Put/Call data."""
    res = delta_client.get_options_chain(underlying_asset=underlying_asset)
    if not res.get("success"):
        return {"error": res.get("error", "Failed to retrieve options chain")}

    contracts = res.get("result", [])
    call_options = []
    put_options = []

    for c in contracts:
        ctype = c.get("contract_type")
        summary = {
            "symbol": c.get("symbol"),
            "product_id": c.get("product_id"),
            "mark_price": c.get("mark_price"),
            "spot_price": c.get("spot_price"),
            "open_interest": c.get("oi_contracts"),
            "greeks": c.get("greeks")
        }
        if ctype == "call_options":
            call_options.append(summary)
        elif ctype == "put_options":
            put_options.append(summary)

    return {
        "success": True,
        "underlying_asset": underlying_asset.upper(),
        "total_calls": len(call_options),
        "total_puts": len(put_options),
        "sample_calls": call_options[:5],
        "sample_puts": put_options[:5]
    }


def tool_check_circuit_breaker() -> Dict[str, Any]:
    """Evaluate account health, daily drawdown, and active position counts against risk limits."""
    acc = tool_get_account_summary()
    if "error" in acc:
        return {"error": acc["error"]}

    total_usdt = acc.get("usdt_total_balance", 0.0)
    open_count = acc.get("active_positions_count", 0)

    decision = risk_manager.check_circuit_breaker(current_equity=total_usdt, open_positions_count=open_count)
    return {"success": True, "circuit_breaker": decision}


def tool_calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    leverage: int = 5,
    risk_pct: Optional[float] = None
) -> Dict[str, Any]:
    """Calculate disciplined contract sizing, dollar risk, and Reward-to-Risk ratio for a trade setup."""
    acc = tool_get_account_summary()
    if "error" in acc:
        return {"error": acc["error"]}

    total_usdt = acc.get("usdt_total_balance", 0.0)
    if total_usdt <= 0:
        return {"error": "Account equity is zero or could not be determined"}

    # Discover contract multiplier from product specs
    pinfo = delta_client.get_product_info(symbol)
    contract_value = float(pinfo.get("contract_value", "0.001")) if pinfo else 0.001

    sizing = risk_manager.calculate_position_size(
        account_equity=total_usdt,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        contract_value=contract_value,
        leverage=leverage,
        risk_pct_override=risk_pct
    )
    sizing["symbol"] = symbol.upper()
    return {"success": True, "sizing": sizing}


def tool_set_leverage(symbol: str, leverage: int) -> Dict[str, Any]:
    """Set leverage for a symbol (enforces maximum allowed leverage ceiling)."""
    clamped_leverage = min(leverage, risk_manager.max_allowed_leverage)
    res = delta_client.set_leverage(symbol, clamped_leverage)
    return {"success": res.get("success", False), "result": res}


def tool_place_order(
    symbol: str,
    size: int,
    side: str,
    order_type: str = "limit_order",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    reduce_only: bool = False
) -> Dict[str, Any]:
    """Place an order on Delta Exchange with pre-execution circuit breaker gate check."""
    # Pre-execution circuit breaker check
    cb = tool_check_circuit_breaker()
    if cb.get("success") and not cb.get("circuit_breaker", {}).get("can_trade", False):
        if not reduce_only:
            return {
                "success": False,
                "error": "ORDER BLOCKED BY CIRCUIT BREAKER GATE",
                "reason": cb["circuit_breaker"].get("reason")
            }

    res = delta_client.place_order(
        symbol=symbol,
        size=size,
        side=side,
        order_type=order_type,
        limit_price=limit_price,
        stop_price=stop_price,
        reduce_only=reduce_only
    )
    return {"success": res.get("success", False), "result": res}


def tool_place_bracket_order(
    symbol: str,
    size: int,
    side: str,
    order_type: str = "limit_order",
    limit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    take_profit_price: Optional[float] = None
) -> Dict[str, Any]:
    """Place entry order with integrated protective Stop-Loss and Take-Profit brackets."""
    cb = tool_check_circuit_breaker()
    if cb.get("success") and not cb.get("circuit_breaker", {}).get("can_trade", False):
        return {
            "success": False,
            "error": "ORDER BLOCKED BY CIRCUIT BREAKER GATE",
            "reason": cb["circuit_breaker"].get("reason")
        }

    res = delta_client.place_bracket_order(
        symbol=symbol,
        size=size,
        side=side,
        order_type=order_type,
        limit_price=limit_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price
    )
    return {"success": res.get("success", False), "result": res}


def tool_cancel_order(symbol: str, order_id: int) -> Dict[str, Any]:
    """Cancel an active order by ID."""
    res = delta_client.cancel_order(symbol, order_id)
    return {"success": res.get("success", False), "result": res}


def tool_cancel_all_orders(symbol: Optional[str] = None) -> Dict[str, Any]:
    """Cancel all open orders, optionally filtered by symbol."""
    res = delta_client.cancel_all_orders(symbol)
    return {"success": res.get("success", False), "result": res}


def tool_close_position(symbol: str) -> Dict[str, Any]:
    """Close an active position immediately using a market order."""
    res = delta_client.close_position(symbol)
    return {"success": res.get("success", False), "result": res}


def tool_journal_trade(
    trade_id: str,
    symbol: str,
    side: str,
    contracts: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    thesis: str,
    strategy: str
) -> Dict[str, Any]:
    """Record trade thesis, risk targets, and execution rationale into trade memory journal."""
    entry = record_trade_entry(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        contracts=contracts,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        thesis=thesis,
        strategy=strategy,
        agent_decision={"recorded_by": "delta_mcp_server"}
    )
    return {"success": True, "journal_entry": entry}


def tool_get_journal_stats() -> Dict[str, Any]:
    """Get trade journal statistics (win rate %, total realized PnL, open vs closed trade history)."""
    return {"success": True, "summary": get_performance_summary()}


# =============================================================================
# FastMCP Integration (If official mcp package installed)
# =============================================================================

def run_fastmcp():
    # pyrefly: ignore[missing-import]
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("delta-exchange-mcp")

    # Register tools
    mcp.tool()(tool_test_connection)
    mcp.tool()(tool_get_account_summary)
    mcp.tool()(tool_get_positions)
    mcp.tool()(tool_get_open_orders)
    mcp.tool()(tool_get_order_history)
    mcp.tool()(tool_get_ticker)
    mcp.tool()(tool_get_orderbook)
    mcp.tool()(tool_get_candles_analysis)
    mcp.tool()(tool_get_options_chain)
    mcp.tool()(tool_check_circuit_breaker)
    mcp.tool()(tool_calculate_position_size)
    mcp.tool()(tool_set_leverage)
    mcp.tool()(tool_place_order)
    mcp.tool()(tool_place_bracket_order)
    mcp.tool()(tool_cancel_order)
    mcp.tool()(tool_cancel_all_orders)
    mcp.tool()(tool_close_position)
    mcp.tool()(tool_journal_trade)
    mcp.tool()(tool_get_journal_stats)

    mcp.run()


# =============================================================================
# Standalone JSON-RPC 2.0 Stdio Handler (Fallback when mcp package is missing)
# =============================================================================

TOOLS_REGISTRY = {
    "delta_test_connection": (tool_test_connection, "Test connection and verify Delta API credentials"),
    "delta_get_account_summary": (tool_get_account_summary, "Get wallet balances (USDT, BTC) and total equity"),
    "delta_get_positions": (tool_get_positions, "Get all open positions with PnL, leverage, and liquidation price"),
    "delta_get_open_orders": (tool_get_open_orders, "List open/pending orders"),
    "delta_get_order_history": (tool_get_order_history, "Get order execution history"),
    "delta_get_ticker": (tool_get_ticker, "Get real-time market ticker data"),
    "delta_get_orderbook": (tool_get_orderbook, "Get Level 2 orderbook depth"),
    "delta_get_candles_analysis": (tool_get_candles_analysis, "Analyze candles with EMA, RSI, ATR, MACD, and regime"),
    "delta_get_options_chain": (tool_get_options_chain, "Get options strikes and Greeks"),
    "delta_check_circuit_breaker": (tool_check_circuit_breaker, "Check daily drawdown and position limits"),
    "delta_calculate_position_size": (tool_calculate_position_size, "Calculate risk-controlled contract sizing"),
    "delta_set_leverage": (tool_set_leverage, "Set leverage for a symbol"),
    "delta_place_order": (tool_place_order, "Place standard limit or market order"),
    "delta_place_bracket_order": (tool_place_bracket_order, "Place order with protective SL and TP brackets"),
    "delta_cancel_order": (tool_cancel_order, "Cancel open order by ID"),
    "delta_cancel_all_orders": (tool_cancel_all_orders, "Cancel all open orders"),
    "delta_close_position": (tool_close_position, "Close position immediately at market"),
    "delta_journal_trade": (tool_journal_trade, "Record trade thesis and execution details into memory"),
    "delta_get_journal_stats": (tool_get_journal_stats, "Get trade journal statistics and history")
}


def run_stdio_jsonrpc():
    """Lightweight native JSON-RPC 2.0 stdio server implementing Model Context Protocol."""
    logger.info("Starting Delta Exchange MCP server (Native JSON-RPC 2.0 Stdio Mode)...")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
                
            line = line.strip()
            if not line:
                continue

            request = json.loads(line)
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # MCP Initialize
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "delta-exchange-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                # Client acknowledging initialization
                continue

            elif method == "tools/list":
                tools_list = []
                for name, (fn, desc) in TOOLS_REGISTRY.items():
                    tools_list.append({
                        "name": name,
                        "description": desc,
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    })
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": tools_list}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                if tool_name in TOOLS_REGISTRY:
                    fn = TOOLS_REGISTRY[tool_name][0]
                    try:
                        result_data = fn(**arguments)
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(result_data, indent=2)
                                    }
                                ]
                            }
                        }
                    except Exception as e:
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps({"error": str(e)}, indent=2)
                                    }
                                ],
                                "isError": True
                            }
                        }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method {tool_name} not found"
                        }
                    }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "ping":
                response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except Exception as e:
            logger.error(f"Error handling request: {e}")


def main():
    try:
        # pyrefly: ignore[missing-import]
        import mcp
        run_fastmcp()
    except ImportError:
        run_stdio_jsonrpc()


if __name__ == "__main__":
    main()
