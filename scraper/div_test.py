"""One-off experiment 4: dividend date/amount data from TradingView's EGX scanner and from Yahoo Finance."""
import json
import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
tickers = json.loads((ROOT / "data" / "tickers.json").read_text(encoding="utf-8"))
URL = "https://scanner.tradingview.com/egypt/scan"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
FIELDS = [
    "dividend_ex_date_recent", "dividend_ex_date_upcoming", "dividend_payment_date_recent", "dividend_payment_date_upcoming",
    "dividend_amount_recent", "dividend_amount_upcoming", "dividends_yield", "dividends_yield_current", "dividends_per_share_fq",
    "dps_common_stock_prim_issue_fy", "dividend_payout_ratio_ttm", "dividend_yield_recent", "dividends_paid_fy", "dividends_per_share_fy",
]
out = {"ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "tv": {}, "yahoo": {}}
for f in FIELDS:
    body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": ["close", f]}
    try:
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
    except Exception as e:  # noqa: BLE001
        out["tv"][f] = {"supported": False, "error": str(e)}
        continue
    if r.status_code != 200:
        out["tv"][f] = {"supported": False, "http": r.status_code}
        continue
    vals = {row["s"].split(":", 1)[1]: row["d"][1] for row in r.json().get("data", [])}
    out["tv"][f] = {"supported": True, "coverage": sum(v is not None for v in vals.values()), "values": vals}

try:
    import yfinance as yf
    for t in tickers:
        try:
            d = yf.Ticker(t["symbol"] + ".CA").dividends
            if d is None or len(d) == 0:
                out["yahoo"][t["symbol"]] = None
                continue
            out["yahoo"][t["symbol"]] = [{"date": str(i.date()), "amount": float(v)} for i, v in list(d.items())[-3:]]
        except Exception as e:  # noqa: BLE001
            out["yahoo"][t["symbol"]] = {"error": str(e)[:80]}
except Exception as e:  # noqa: BLE001
    out["yahoo_error"] = str(e)[:200]
(ROOT / "data" / "div_test.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v.get("coverage") if v.get("supported") else "no") for k, v in out["tv"].items()})
print("yahoo with dividends:", sum(1 for v in out["yahoo"].values() if isinstance(v, list)))
