"""One-off experiment 5: growth fields, analyst rating, and whole-market scan for sector P/E medians."""
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
    "earnings_per_share_diluted_yoy_growth_ttm", "earnings_per_share_diluted_yoy_growth_fy", "earnings_per_share_diluted_yoy_growth_fq",
    "total_revenue_yoy_growth_ttm", "total_revenue_yoy_growth_fy", "total_revenue_yoy_growth_fq",
    "net_income_yoy_growth_fy", "net_income_yoy_growth_ttm", "gross_margin_ttm", "net_margin_ttm", "operating_margin_ttm",
    "recommendation_mark", "net_income_ttm", "net_income_fy", "total_revenue_ttm", "total_revenue_fy",
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

# whole-market scan: sector + P/E for every stock the scanner knows in Egypt
try:
    body = {"columns": ["name", "sector", "price_earnings_ttm", "close", "market_cap_basic", "type"], "range": [0, 1000],
            "filter": [{"left": "type", "operation": "equal", "right": "stock"}]}
    r = requests.post(URL, json=body, headers=HEADERS, timeout=60)
    out["universe_http"] = r.status_code
    if r.status_code == 200:
        data = r.json().get("data", [])
        out["universe"] = [{"s": row["s"], "d": row["d"]} for row in data]
        out["universe_count"] = len(data)
    else:
        out["universe_body"] = r.text[:200]
except Exception as e:  # noqa: BLE001
    out["universe_error"] = str(e)[:200]
(ROOT / "data" / "auto_test.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v.get("coverage") if v.get("supported") else "no") for k, v in out["fields"].items()})
print("universe:", out.get("universe_http"), out.get("universe_count"))
