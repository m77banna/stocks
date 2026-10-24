"""One-off experiment 3: analyst price targets and earnings fields on TradingView's EGX scanner."""
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
    "price_target_average", "price_target_high", "price_target_low", "price_target_median", "price_target_1y",
    "recommendation_mark", "recommendation_total", "price_earnings_ttm", "earnings_per_share_basic_ttm",
    "earnings_per_share_diluted_ttm", "earnings_per_share_diluted_fy", "earnings_per_share_basic_fy",
    "earnings_per_share_forecast_next_fy", "earnings_per_share_forecast_next_fq", "net_income_ttm", "net_income_fy",
    "price_earnings_forward", "Recommend.All", "Recommend.MA", "Recommend.Other",
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
(ROOT / "data" / "tv_fields.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: (v.get("coverage") if v.get("supported") else "no") for k, v in out["fields"].items()})
