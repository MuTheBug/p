#!/usr/bin/env python3
"""
Binance API Connection Diagnostic Tool

Helps troubleshoot API key issues and connection problems.
"""

import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def check_api_keys():
    """Check if API keys are configured."""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    print("=" * 50)
    print("BINANCE API DIAGNOSTIC")
    print("=" * 50)

    # Check if keys exist
    if not api_key:
        print("❌ BINANCE_API_KEY is not set")
        return False
    if not api_secret:
        print("❌ BINANCE_API_SECRET is not set")
        return False

    print(f"✓ API Key found: {api_key[:8]}...{api_key[-4:]}")
    print(f"✓ API Secret found: {api_secret[:4]}...{api_secret[-4:]}")

    # Check for common issues
    if " " in api_key or " " in api_secret:
        print("⚠️  WARNING: API key contains spaces - this may cause issues")

    if len(api_key) < 60:
        print(f"⚠️  WARNING: API key seems short ({len(api_key)} chars) - typical length is 64")

    if len(api_secret) < 60:
        print(f"⚠️  WARNING: API secret seems short ({len(api_secret)} chars) - typical length is 64")

    return True


def test_connection(testnet: bool):
    """Test connection to Binance."""
    from binance_futures import BinanceFuturesClient, BinanceFuturesError

    env_name = "TESTNET" if testnet else "PRODUCTION"
    print(f"\n--- Testing {env_name} connection ---")

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    client = BinanceFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet
    )

    # Test 1: Public endpoint (no auth)
    print("\n1. Testing public endpoint (no auth required)...")
    try:
        price = client.get_ticker_price("BTCUSDT")
        print(f"   ✓ Public API working - BTC price: ${float(price['price']):,.2f}")
    except Exception as e:
        print(f"   ❌ Public API failed: {e}")
        return False

    # Test 2: Account endpoint (auth required)
    print("\n2. Testing authenticated endpoint...")
    try:
        account = client.get_account()
        balance = float(account.get("totalWalletBalance", 0))
        print(f"   ✓ Authentication successful!")
        print(f"   ✓ Account balance: ${balance:,.2f}")
        return True
    except BinanceFuturesError as e:
        print(f"   ❌ Authentication failed: {e}")

        if e.code == -2015:
            print("\n   DIAGNOSIS for error -2015:")
            print("   ─────────────────────────────")
            if testnet:
                print("   • You're connecting to TESTNET")
                print("   • Make sure you're using TESTNET API keys from:")
                print("     https://testnet.binancefuture.com/")
                print("   • Production keys will NOT work on testnet")
            else:
                print("   • You're connecting to PRODUCTION")
                print("   • Make sure you're using PRODUCTION API keys from:")
                print("     https://www.binance.com/en/my/settings/api-management")
                print("   • Testnet keys will NOT work on production")

            print("\n   Other things to check:")
            print("   • API key has 'Enable Futures' permission")
            print("   • IP whitelist includes your current IP (or is unrestricted)")
            print("   • API key is not expired or deleted")

        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False


def get_my_ip():
    """Get current public IP."""
    import requests
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=5)
        ip = response.json().get("ip")
        print(f"\nYour public IP: {ip}")
        print("Make sure this IP is whitelisted in your Binance API settings")
        print("(or leave IP whitelist empty for unrestricted access)")
    except:
        print("\nCould not determine your public IP")


def main():
    print("\nThis tool will help diagnose Binance API connection issues.\n")

    # Check keys
    if not check_api_keys():
        print("\n❌ Please set your API keys in .env file first")
        sys.exit(1)

    # Get IP
    get_my_ip()

    # Check testnet setting
    use_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    print(f"\nConfigured mode: {'TESTNET' if use_testnet else 'PRODUCTION'}")

    # Test both environments
    print("\n" + "=" * 50)
    print("TESTING CONNECTIONS")
    print("=" * 50)

    # Test configured environment first
    success = test_connection(use_testnet)

    if not success:
        # Try the other environment
        other_env = not use_testnet
        print(f"\n\n💡 Let's try {'TESTNET' if other_env else 'PRODUCTION'} instead...")
        other_success = test_connection(other_env)

        if other_success:
            print(f"\n✅ SUCCESS! Your API keys work with {'TESTNET' if other_env else 'PRODUCTION'}")
            print(f"   Update your .env file: BINANCE_TESTNET={'true' if other_env else 'false'}")
        else:
            print("\n❌ Connection failed on both environments")
            print("\nPossible solutions:")
            print("1. Generate new API keys from Binance")
            print("2. Ensure 'Enable Futures' is checked in API permissions")
            print("3. Remove IP restrictions or add your IP to whitelist")
            print("4. If using testnet, get keys from: https://testnet.binancefuture.com/")
    else:
        print(f"\n✅ SUCCESS! Connection to {'TESTNET' if use_testnet else 'PRODUCTION'} is working!")


if __name__ == "__main__":
    main()
