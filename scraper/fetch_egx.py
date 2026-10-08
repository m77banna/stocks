"""
Fetches prices for the tickers in data/tickers.json from TradingView's public
EGX scanner (data is delayed ~15 minutes) and writes data/latest.json.
If TradingView fails, the existing latest.json is left untouched.
"""
import json
import sys
import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TICKERS_FILE = ROOT / "data" / "tickers.json"
OUTPUT_FILE = ROOT / "data" / "latest.json"

URL = "https://scanner.tradingview.com/egypt/scan"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
COLUMN_SETS = [
    ["close", "change", "volume", "market_cap_basic"],
    ["close", "change", "volume"],
]


def fetch(tickers):
    for cols in COLUMN_SETS:
        body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": cols}
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return cols, r.json().get("data", [])
        print(f"[warn] columns {cols}: HTTP {r.status_code} {r.text[:150]}")
    return None, None


def main():
    tickers = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    cols, data = fetch(tickers)
    if data is None:
        print("TradingView request failed; keeping the existing latest.json")
        sys.exit(1)
    rows = {}
    for row in data:
        sym = row["s"].split(":", 1)[1]
        rows[sym] = dict(zip(cols, row["d"]))
    stocks = []
    for t in tickers:
        r = rows.get(t["symbol"])
        if not r or r.get("close") is None:
            stocks.append({"symbol": t["symbol"], "error": "no_data"})
            continue
        item = {"symbol": t["symbol"], "price": round(float(r["close"]), 3)}
        if r.get("change") is not None:
            item["change_pct"] = round(float(r["change"]), 2)
        if r.get("volume") is not None:
            item["volume"] = int(r["volume"])
        if r.get("market_cap_basic"):
            item["cap_bn"] = round(r["market_cap_basic"] / 1e9, 2)
        stocks.append(item)
    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "TradingView (delayed ~15 min)",
        "stocks": stocks,
    }
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for s in stocks if "error" not in s)
    print(f"Wrote {OUTPUT_FILE} - {ok}/{len(stocks)} tickers")


if __name__ == "__main__":
    main()
