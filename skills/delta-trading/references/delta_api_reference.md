# Delta Exchange API v2 Technical Reference

## 1. Authentication Architecture

Delta Exchange authenticates all private REST API endpoints using HMAC-SHA256 signatures.

### Signature Data Formula
$$\text{Signature String} = \text{METHOD} + \text{TIMESTAMP} + \text{PATH} + \text{QUERY\_STRING} + \text{BODY}$$

- **METHOD**: Uppercase HTTP verb (`GET`, `POST`, `DELETE`, `PUT`)
- **TIMESTAMP**: Unix epoch time in seconds (`str(int(time.time()))`)
- **PATH**: Endpoint path starting with `/v2/...`
- **QUERY_STRING**: Leading `?` followed by urlencoded query parameters (e.g. `?state=open`), or empty string `""` if no parameters.
- **BODY**: Exact JSON stringified payload (using `json.dumps(payload, separators=(',', ':'))`), or empty string `""` if no body.

### Required HTTP Headers
```http
api-key: <DELTA_API_KEY>
timestamp: <UNIX_TIMESTAMP_SECONDS>
signature: <HMAC_SHA256_HEX_DIGEST>
Content-Type: application/json
User-Agent: Delta-Exchange-MCP-Client/1.0
```

## 2. Base URLs
- **India Live**: `https://api.india.delta.exchange`
- **Global Live**: `https://api.delta.exchange`
- **Testnet Global**: `https://testnet-api.delta.exchange`
- **Testnet India**: `https://cdn-ind.testnet.deltaex.org`

## 3. Key Endpoints

| Category | Endpoint | Method | Description |
|---|---|---|---|
| Public Products | `/v2/products` | GET | List all active contracts, contract values, tick sizes |
| Public Tickers | `/v2/tickers/{symbol}` | GET | Real-time mark price, 24h stats, funding rate |
| Public L2 Book | `/v2/l2orderbook/{symbol}` | GET | Bids and asks depth |
| Public Chart | `/v2/chart/history` | GET | OHLCV candlesticks (`from`, `to`, `resolution`) |
| Balances | `/v2/wallet/balances` | GET | Balances across assets (USDT, BTC, etc.) |
| Positions | `/v2/positions/margined` | GET | Open margined futures & options positions |
| Orders | `/v2/orders` | GET | Active open orders (`?state=open`) |
| Place Order | `/v2/orders` | POST | Place limit/market order with optional bracket SL/TP |
| Leverage | `/v2/products/{product_id}/orders/leverage` | POST | Update leverage multiplier |
| Cancel Order | `/v2/orders` | DELETE | Cancel single order (`id`, `product_id`) |
| Cancel All | `/v2/orders/all` | DELETE | Cancel all open orders for product |
| Close Position | `/v2/positions/close` | POST | Market close entire open position |
