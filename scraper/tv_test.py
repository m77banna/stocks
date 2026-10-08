"""One-off experiment: fetch the 37 tickers from TradingView's EGX scanner and
compare close prices with the Yahoo-based data/latest.json."""
import json
import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
tickers = json.loads((ROOT / "data" / "tickers.json").read_text(encoding="utf-8"))
yahoo = {}
lp = ROOT / "data" / "latest.json"
if lp.exists():
    for s in json.loads(lp.read_text(encoding="utf-8")).get("stocks", []):
        if "error" not in s:
            yahoo[s["symbol"]] = s

URL = "https://scanner.tradingview.com/egypt/scan"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}
COLUMN_SETS = [
    ["close", "change", "volume", "market_cap_basic", "price_earnings_ttm", "earnings_per_share_basic_ttm", "update_mode"],
    ["close", "change", "volume", "market_cap_basic", "price_earnings_ttm"],
    ["close", "change", "volume"],
]

out = {"ran_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "attempts": []}
data = None
for cols in COLUMN_SETS:
    body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": cols}
    try:
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
        out["attempts"].append({"columns": cols, "http": r.status_code, "body_head": r.text[:200] if r.status_code != 200 else ""})
        if r.status_code == 200:
            data = r.json().get("data", [])
            out["columns"] = cols
            break
    except Exception as e:  # noqa: BLE001
        out["attempts"].append({"columns": cols, "error": str(e)})

results, comparison = {}, []
if data is not None:
    for row in data:
        sym = row["s"].split(":", 1)[1]
        results[sym] = dict(zip(out["columns"], row["d"]))
    for t in tickers:
        s = t["symbol"]
        tv = results.get(s, {}).get("close")
        y = yahoo.get(s, {}).get("price")
        diff = round((tv - y) / y * 100, 2) if tv is not None and y else None
        comparison.append({"symbol": s, "tv_price": tv, "yahoo_price": y, "diff_pct": diff})
    out["missing"] = [t["symbol"] for t in tickers if t["symbol"] not in results]
out["comparison"] = comparison
out["results"] = results
(ROOT / "data" / "tv_test.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("tv ok:", len(results), "of", len(tickers), "| attempts:", [a.get("http", a.get("error")) for a in out["attempts"]])
