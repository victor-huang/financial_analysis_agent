#!/usr/bin/env python3
"""
TradingView WebSocket client to capture financial data.
The forecast page uses WebSocket to load financial/forecast data.

Requirements:
    pip install websocket-client
"""

import json
import time
import re
from typing import Dict, List, Optional

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False
    print("websocket-client not installed. Install with: pip install websocket-client")


class TradingViewWebSocketClient:
    """Client to connect to TradingView WebSocket and retrieve financial data."""

    def __init__(self):
        self.ws_url = "wss://pushstream.tradingview.com/message-pipe-ws/public"
        self.messages_received = []
        self.financial_data = {}

    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            # TradingView uses a custom protocol with ~m~ prefix
            # Format: ~m~<length>~m~<json_data>
            print(f"\n[RAW MESSAGE] {message[:200]}...")

            # Parse the custom protocol
            if message.startswith("~m~"):
                parts = message.split("~m~")
                if len(parts) >= 3:
                    json_str = parts[2]
                    try:
                        data = json.loads(json_str)
                        print(f"\n[PARSED] {json.dumps(data, indent=2)[:500]}")

                        # Check if this is financial data
                        if self._is_financial_data(data):
                            print("\n✓ FOUND FINANCIAL DATA!")
                            print(json.dumps(data, indent=2))
                            self.financial_data = data

                        self.messages_received.append(data)
                    except json.JSONDecodeError:
                        print(f"[INFO] Non-JSON message: {json_str[:100]}")

        except Exception as e:
            print(f"[ERROR] Processing message: {e}")

    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"\n[ERROR] WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        print(f"\n[INFO] WebSocket closed: {close_status_code} - {close_msg}")

    def _on_open(self, ws):
        """Handle WebSocket connection open."""
        print("[INFO] WebSocket connected!")

        # Send subscription message for financial data
        # Format based on TradingView's protocol
        symbol = "NASDAQ:MU"

        # Try different subscription patterns
        subscriptions = [
            {
                "m": "quote_add_symbols",
                "p": [symbol]
            },
            {
                "m": "symbol_financials",
                "p": [symbol, {"annual": True, "quarterly": True}]
            },
            {
                "m": "request_financials",
                "p": [symbol]
            },
        ]

        for sub in subscriptions:
            message = f"~m~{len(json.dumps(sub))}~m~{json.dumps(sub)}"
            print(f"\n[SEND] {message}")
            ws.send(message)
            time.sleep(0.5)

    def _is_financial_data(self, data: Dict) -> bool:
        """Check if the data contains financial information."""
        if not isinstance(data, dict):
            return False

        # Check for financial keywords
        data_str = json.dumps(data).lower()
        return any(keyword in data_str for keyword in [
            'revenue', 'earnings', 'eps', 'fiscal', 'annual', 'quarterly', 'forecast'
        ])

    def connect_and_listen(self, duration=30):
        """
        Connect to WebSocket and listen for messages.

        Args:
            duration: How long to listen in seconds
        """
        if not HAS_WEBSOCKET:
            print("ERROR: websocket-client not installed")
            print("Install with: pip install websocket-client")
            return

        print("="*80)
        print("TradingView WebSocket Client")
        print("="*80)
        print(f"Connecting to: {self.ws_url}")
        print(f"Will listen for {duration} seconds...")

        # websocket.enableTrace(True)  # Uncomment for verbose debug logs

        ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open
        )

        # Run with timeout
        import threading
        wst = threading.Thread(target=ws.run_forever)
        wst.daemon = True
        wst.start()

        print(f"\n[INFO] Listening for {duration} seconds...")
        time.sleep(duration)

        ws.close()
        print(f"\n[INFO] Captured {len(self.messages_received)} messages")

        return self.financial_data


def alternative_approach_manual_capture():
    """
    Provide instructions for manual WebSocket capture.
    """
    print("\n" + "="*80)
    print("ALTERNATIVE: Manual WebSocket Capture")
    print("="*80)
    print("""
Since TradingView's WebSocket protocol may be complex, try manual capture:

1. Open Chrome and navigate to:
   https://www.tradingview.com/symbols/NASDAQ-MU/forecast/

2. Open DevTools (F12) and go to the "Network" tab

3. Filter by "WS" (WebSocket)

4. Refresh the page

5. Click on the WebSocket connection (usually to pushstream.tradingview.com)

6. Go to the "Messages" tab

7. Look through the messages for ones containing:
   - "revenue"
   - "earnings"
   - "eps"
   - "fiscal"
   - Financial arrays

8. Copy the message content and structure

9. Share it so we can:
   - Understand the message format
   - Create a proper subscription request
   - Parse the response data

WHAT TO LOOK FOR:
- Messages with "m": "financial_data" or similar
- Arrays of historical revenue/earnings values
- Fiscal year/quarter identifiers
- Request format that triggers the data response
    """)


def main():
    """Main execution."""
    if not HAS_WEBSOCKET:
        print("\n✗ websocket-client not installed")
        print("\nInstall it with:")
        print("  pip install websocket-client")
        print("\nThen run this script again")
        alternative_approach_manual_capture()
        return

    print("Attempting automated WebSocket capture...")
    print("(This may not work if TradingView requires authentication or uses a complex protocol)")
    print()

    client = TradingViewWebSocketClient()
    financial_data = client.connect_and_listen(duration=30)

    if financial_data:
        print("\n" + "="*80)
        print("SUCCESS! Financial data captured:")
        print("="*80)
        print(json.dumps(financial_data, indent=2))

        # Save to file
        with open("tradingview_websocket_data.json", "w") as f:
            json.dump({
                "financial_data": financial_data,
                "all_messages": client.messages_received
            }, f, indent=2)
        print("\n✓ Saved to: tradingview_websocket_data.json")
    else:
        print("\n" + "="*80)
        print("No financial data captured automatically")
        print("="*80)
        alternative_approach_manual_capture()


if __name__ == "__main__":
    main()
