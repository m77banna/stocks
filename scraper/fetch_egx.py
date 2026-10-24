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
    ["close", "change", "volume", "market_cap_basic", "description", "sector", "price_earnings_ttm"],
    ["close", "change", "volume", "market_cap_basic", "description", "sector"],
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


EXTRA_COLUMNS = [
    "earnings_per_share_basic_ttm", "earnings_per_share_diluted_fy", "price_target_average",
    "price_target_high", "price_target_low", "recommendation_total",
]


def fetch_extra(tickers):
    """Earnings and analyst-target fields, in a separate request so a failure never affects prices."""
    try:
        body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": EXTRA_COLUMNS}
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"[warn] extra fields: HTTP {r.status_code}")
            return {}
        return {row["s"].split(":", 1)[1]: dict(zip(EXTRA_COLUMNS, row["d"])) for row in r.json().get("data", [])}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] extra fields failed: {e}")
        return {}


def pick_pe(price, pe_ttm, eps_ttm, eps_fy):
    """Best available P/E and where it came from."""
    if pe_ttm is not None and pe_ttm > 0:
        return float(pe_ttm), "ttm"
    if eps_ttm is not None and eps_ttm > 0 and price:
        return price / eps_ttm, "eps_ttm"
    if eps_fy is not None and eps_fy > 0 and price:
        return price / eps_fy, "eps_fy"
    return None, None


def fetch_technical(tickers):
    """TradingView technical rating (-1..1). Separate request so a failure never affects prices."""
    try:
        body = {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": ["Recommend.All"]}
        r = requests.post(URL, json=body, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"[warn] technical rating: HTTP {r.status_code}")
            return {}
        return {row["s"].split(":", 1)[1]: row["d"][0] for row in r.json().get("data", []) if row["d"][0] is not None}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] technical rating failed: {e}")
        return {}


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
    tech = fetch_technical(tickers)
    extra = fetch_extra(tickers)
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
        if r.get("description"):
            item["name"] = r["description"]
        if r.get("sector"):
            item["sector"] = r["sector"]
        ex = extra.get(t["symbol"], {})
        pe, pe_src = pick_pe(item["price"], r.get("price_earnings_ttm"), ex.get("earnings_per_share_basic_ttm"), ex.get("earnings_per_share_diluted_fy"))
        if pe is not None:
            item["pe"] = round(pe, 2)
            item["pe_src"] = pe_src
        if ex.get("price_target_average"):
            item["target"] = round(float(ex["price_target_average"]), 2)
            if ex.get("price_target_low"):
                item["target_lo"] = round(float(ex["price_target_low"]), 2)
            if ex.get("price_target_high"):
                item["target_hi"] = round(float(ex["price_target_high"]), 2)
            if ex.get("recommendation_total"):
                item["target_n"] = int(ex["recommendation_total"])
        if t["symbol"] in tech:
            item["tech"] = round(float(tech[t["symbol"]]), 3)
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
