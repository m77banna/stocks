"""One-off experiment 2: annual (fiscal-year) fundamentals and dividend fields for the EGX tickers."""
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
    "total_equity_fy", "total_assets_fy", "total_debt_fy", "total_current_assets_fy", "total_current_liabilities_fy",
    "net_income_fy", "total_revenue_fy", "dps_common_stock_prim_issue_fy", "dividends_per_share_fq",
    "dividend_payout_ratio_ttm", "dividends_yield", "dividends_yield_current", "earnings_per_share_basic_ttm",
    "earnings_per_share_diluted_ttm", "earnings_per_share_diluted_fy", "book_value_per_share_fy",
    "price_book_fy", "current_ratio_fy", "debt_to_equity_fy", "return_on_equity_fy", "total_shares_outstanding",
    "total_shares_outstanding_fundamental", "float_shares_outstanding", "free_cash_flow_fy", "cash_f_operating_activities_fy",
    "earnings_per_share_diluted_yoy_growth_fy", "total_revenue_yoy_growth_fy", "goodwill_fy", "long_term_debt_fy",
    "net_income_fq", "total_equity_fq",
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
        out["fields"][f] = {"supported": False, "http": r.status_code}
        continue
    vals = {row["s"].split(":", 1)[1]: row["d"][1] for row in r.json().get("data", [])}
    out["fields"][f] = {"supported": True, "coverage": sum(v is not None for v in vals.values()), "values": vals}
(ROOT / "data" / "tv_fund2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v.get("coverage") if v.get("supported") else "no") for k, v in out["fields"].items()})
