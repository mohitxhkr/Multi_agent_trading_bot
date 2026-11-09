#!/usr/bin/env python3
"""
Diagnostic test script for Delta Exchange API connectivity and credentials.
Run:
    python test_delta_connection.py
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_client import DeltaExchangeClient


def main():
    print("=" * 60)
    print("  DELTA EXCHANGE API DIAGNOSTIC & VERIFICATION TOOL")
    print("=" * 60)
    
    client = DeltaExchangeClient()
    print(f"\n1. Target Environment : {client.environment.upper()}")
    print(f"2. Base URL            : {client.base_url}")
    
    print("\n3. Testing Public Connectivity...")
    products = client.load_products()
    if products:
        print(f"   [SUCCESS] Connected to Delta Exchange. Cached {len(products)} tradable products.")
    else:
        print("   [FAILED] Could not retrieve products from Delta Exchange.")

    print("\n4. Testing Live Ticker & Orderbook...")
    ticker = client.get_ticker("BTCUSDT")
    if ticker.get("success"):
        tick_data = ticker.get("result", {})
        price = tick_data.get("close") or tick_data.get("mark_price")
        print(f"   [SUCCESS] BTCUSDT Ticker received. Latest Price: ${price}")
    else:
        print(f"   [WARNING] BTCUSDT Ticker query returned: {ticker.get('error')}")

    print("\n5. Testing API Authentication (Private Endpoints)...")
    if not client.api_key or not client.api_secret:
        print("   [INFO] API Key and Secret are not set in .env yet.")
        print("   To enable authenticated trading and balance checks:")
        print("   - Copy .env.example to .env")
        print("   - Set DELTA_API_KEY and DELTA_API_SECRET")
    else:
        auth_test = client.get_wallet_balances()
        if auth_test.get("success"):
            print("   [SUCCESS] Authenticated successfully with Delta Exchange!")
            balances = auth_test.get("result", [])
            print(f"   Found {len(balances)} asset wallets:")
            for b in balances:
                if float(b.get("balance", 0)) > 0:
                    print(f"    • {b.get('asset_symbol')}: Total={b.get('balance')}, Available={b.get('available_balance')}")
        else:
            print(f"   [AUTH FAILED] {auth_test.get('error')}")
            print("   Please check your API key, secret, and system clock synchronization.")

    print("\n" + "=" * 60)
    print("Diagnostic complete.")


if __name__ == "__main__":
    main()
