"""
Pulls the latest daily close for each ticker in data/tickers.json from
Yahoo Finance and writes data/latest.json.

Uses the `history` endpoint (not `.info` / `fast_info`), because Yahoo's
quote endpoint has been observed to return stale/wrong data for .CA
(Egyptian Exchange) symbols. See README.md for details.
"""
import json
import time
import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
TICKERS_FILE = ROOT / "data" / "tickers.json"
OUTPUT_FILE = ROOT / "data" / "latest.json"


def fetch_one(yahoo_symbol: str):
    t = yf.Ticker(yahoo_symbol)
    hist = t.history(period="10d", auto_adjust=False)
    if hist.empty:
        return None
    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last
    price = round(float(last["Close"]), 2)
    prev_close = round(float(prev["Close"]), 2)
    change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else None
    volume = int(last["Volume"]) if not hist["Volume"].isna().all() else 0
    session_date = hist.index[-1].strftime("%Y-%m-%d")
    return {
        "price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "volume": volume,
        "session_date": session_date,
    }


def main():
    tickers = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    stocks = []
    for t in tickers:
        time.sleep(0.5)
        try:
            data = fetch_one(t["yahoo"])
        except Exception as e:  # noqa: BLE001
            data = None
            print(f"[warn] {t['symbol']} ({t['yahoo']}): {e}")
        if data is None:
            stocks.append({"symbol": t["symbol"], "error": "no_data"})
            continue
        stocks.append({"symbol": t["symbol"], **data})

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stocks": stocks,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for s in stocks if "error" not in s)
    print(f"Wrote {OUTPUT_FILE} — {ok}/{len(stocks)} tickers fetched successfully")


if __name__ == "__main__":
    main()
