"""One-off experiment: which fundamental fields does TradingView's EGX scanner return, and for how many tickers?"""
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
    "price_book_fq", "book_value_per_share_fq", "return_on_equity_fq", "total_assets_fq", "total_debt_fq",
    "net_debt_fq", "debt_to_equity_fq", "total_equity_fq", "total_current_assets_fq", "total_current_liabilities_fq",
    "cash_n_short_term_invest_fq", "dividend_yield_recent", "price_sales_current", "net_income_fy",
    "total_revenue_fy", "return_on_assets_fq", "current_ratio_fq", "price_earnings_ttm",
]
out = {"ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "fields": {}}
for f in FIELDS:
    body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": ["close", f]}
    try:
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
    except Exception as e:  # noqa: BLE001
        out["fields"][f] = {"supported": False, "error": str(e)}
        continue
    if r.status_code != 200:
        out["fields"][f] = {"supported": False, "http": r.status_code, "body": r.text[:120]}
        continue
    vals = {row["s"].split(":", 1)[1]: row["d"][1] for row in r.json().get("data", [])}
    out["fields"][f] = {"supported": True, "coverage": sum(v is not None for v in vals.values()), "values": vals}
(ROOT / "data" / "tv_fund.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v.get("coverage") if v.get("supported") else "no") for k, v in out["fields"].items()})
