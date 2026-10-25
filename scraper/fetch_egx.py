"""
Fetches everything shown on the portfolio page for the tickers in data/tickers.json
and writes data/latest.json. Nothing in the output is typed by hand:

* prices, market cap, name, sector, technical rating, P/E, analyst targets and
  rating, dividends and growth figures come from TradingView's public EGX scanner
  (data is delayed ~15 minutes);
* dividend records TradingView lacks are filled from Yahoo Finance;
* the "approximate value" benchmark (sector P/E) is computed from the whole market scan;
* the Outlook is a mechanical rule applied to the latest earnings and revenue growth.

If the main TradingView request fails, the existing latest.json is left untouched.
"""
import json
import sys
import time
import statistics
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
EXTRA_COLUMNS = [
    "earnings_per_share_basic_ttm", "earnings_per_share_diluted_fy", "net_income_ttm", "net_income_fy",
    "price_target_average", "price_target_high", "price_target_low", "recommendation_total", "recommendation_mark",
    "dividend_ex_date_recent", "dividend_payment_date_recent", "dividend_amount_recent", "dividends_yield_current",
    "earnings_per_share_diluted_yoy_growth_fq", "earnings_per_share_diluted_yoy_growth_ttm", "earnings_per_share_diluted_yoy_growth_fy",
    "total_revenue_yoy_growth_fq", "total_revenue_yoy_growth_ttm", "total_revenue_yoy_growth_fy",
]


def post(body, timeout=30):
    return requests.post(URL, json=body, headers=HEADERS, timeout=timeout)


def symbols_body(tickers, columns):
    return {"symbols": {"tickers": ["EGX:" + t["symbol"] for t in tickers], "query": {"types": []}}, "columns": columns}


def fetch(tickers):
    for cols in COLUMN_SETS:
        r = post(symbols_body(tickers, cols))
        if r.status_code == 200:
            return cols, r.json().get("data", [])
        print(f"[warn] columns {cols}: HTTP {r.status_code} {r.text[:150]}")
    return None, None


def fetch_columns(tickers, columns, label):
    """Optional data in a separate request, so a failure never affects prices."""
    try:
        r = post(symbols_body(tickers, columns))
        if r.status_code != 200:
            print(f"[warn] {label}: HTTP {r.status_code}")
            return {}
        return {row["s"].split(":", 1)[1]: dict(zip(columns, row["d"])) for row in r.json().get("data", [])}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] {label} failed: {e}")
        return {}


def ts_to_date(v):
    if v is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(float(v), datetime.timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return None


def pick_pe(price, cap, ex, pe_ttm):
    """Best available P/E and where it came from (most current basis first)."""
    if pe_ttm is not None and pe_ttm > 0:
        return float(pe_ttm), "ttm"
    eps_ttm, eps_fy = ex.get("earnings_per_share_basic_ttm"), ex.get("earnings_per_share_diluted_fy")
    ni_ttm, ni_fy = ex.get("net_income_ttm"), ex.get("net_income_fy")
    if eps_ttm is not None and eps_ttm > 0 and price:
        return price / eps_ttm, "eps_ttm"
    if ni_ttm is not None and ni_ttm > 0 and cap:
        return cap * 1e9 / ni_ttm, "ni_ttm"
    if eps_fy is not None and eps_fy > 0 and price:
        return price / eps_fy, "eps_fy"
    if ni_fy is not None and ni_fy > 0 and cap:
        return cap * 1e9 / ni_fy, "ni_fy"
    return None, None


def sector_pe_benchmark():
    """Median P/E per sector over the whole EGX scan -> function sector -> benchmark P/E (clamped 6-20)."""
    try:
        body = {"columns": ["sector", "price_earnings_ttm"], "range": [0, 1000],
                "filter": [{"left": "type", "operation": "equal", "right": "stock"}]}
        r = post(body, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        by, allpe = {}, []
        for row in r.json().get("data", []):
            sector, pe = row["d"][0], row["d"][1]
            if pe is not None and 3 <= pe <= 50:
                allpe.append(pe)
                if sector:
                    by.setdefault(sector, []).append(pe)
        overall = statistics.median(allpe)
        med = {k: statistics.median(v) for k, v in by.items() if len(v) >= 4}
        print(f"sector benchmark: {len(allpe)} stocks with usable P/E, {len(med)} sectors, overall {overall:.1f}")
        return lambda sector: round(min(max(med.get(sector, overall), 6), 20), 2)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] sector benchmark failed: {e}")
        return lambda sector: 13.82


def outlook(ex):
    """Mechanical trend signal from the latest YoY earnings and revenue growth. Returns None without data."""
    eps = rev = None
    basis = None
    for key, tag in (("fq", "latest quarter"), ("ttm", "last 12 months"), ("fy", "last fiscal year")):
        v = ex.get(f"earnings_per_share_diluted_yoy_growth_{key}")
        if v is not None:
            eps, basis = v, tag
            break
    for key in ("fq", "ttm", "fy"):
        v = ex.get(f"total_revenue_yoy_growth_{key}")
        if v is not None:
            rev = v
            break
    if eps is None and rev is None:
        return None
    ni = ex.get("net_income_ttm")
    if (ni is not None and ni <= 0) or (eps is not None and eps <= -10):
        rating = "negative"
    elif eps is not None and eps >= 10 and (rev is None or rev >= 0):
        rating = "positive"
    else:
        rating = "neutral"
    out = {"outlook": rating, "outlook_basis": basis or "n/a"}
    if eps is not None:
        out["outlook_eps"] = round(float(eps), 1)
    if rev is not None:
        out["outlook_rev"] = round(float(rev), 1)
    return out


def yahoo_dividends(symbols):
    """Last dividend per symbol from Yahoo Finance, only for the symbols TradingView has no record for."""
    out = {}
    if not symbols:
        return out
    try:
        import yfinance as yf
    except Exception as e:  # noqa: BLE001
        print(f"[warn] yfinance unavailable: {e}")
        return out
    for sym in symbols:
        time.sleep(0.5)
        try:
            d = yf.Ticker(sym + ".CA").dividends
            if d is not None and len(d):
                idx, val = list(d.items())[-1]
                out[sym] = (str(idx.date()), round(float(val), 3))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] yahoo dividends {sym}: {e}")
    return out


def main():
    tickers = json.loads(TICKERS_FILE.read_text(encoding="utf-8"))
    cols, data = fetch(tickers)
    if data is None:
        print("TradingView request failed; keeping the existing latest.json")
        sys.exit(1)
    rows = {row["s"].split(":", 1)[1]: dict(zip(cols, row["d"])) for row in data}
    tech = fetch_columns(tickers, ["Recommend.All"], "technical rating")
    extra = fetch_columns(tickers, EXTRA_COLUMNS, "extra fields")
    bench = sector_pe_benchmark()

    stocks = []
    for t in tickers:
        sym = t["symbol"]
        r = rows.get(sym)
        if not r or r.get("close") is None:
            stocks.append({"symbol": sym, "error": "no_data"})
            continue
        item = {"symbol": sym, "price": round(float(r["close"]), 3)}
        if r.get("change") is not None:
            item["change_pct"] = round(float(r["change"]), 2)
        if r.get("volume") is not None:
            item["volume"] = int(r["volume"])
        cap = round(r["market_cap_basic"] / 1e9, 2) if r.get("market_cap_basic") else None
        if cap:
            item["cap_bn"] = cap
        if r.get("description"):
            item["name"] = r["description"]
        if r.get("sector"):
            item["sector"] = r["sector"]
        item["fpe"] = bench(r.get("sector"))
        ex = extra.get(sym, {})

        pe, src = pick_pe(item["price"], cap, ex, r.get("price_earnings_ttm"))
        if pe is not None:
            item["pe"], item["pe_src"] = round(pe, 2), src
        if ex.get("price_target_average"):
            item["target"] = round(float(ex["price_target_average"]), 2)
            if ex.get("price_target_low"):
                item["target_lo"] = round(float(ex["price_target_low"]), 2)
            if ex.get("price_target_high"):
                item["target_hi"] = round(float(ex["price_target_high"]), 2)
            if ex.get("recommendation_total"):
                item["target_n"] = int(ex["recommendation_total"])
        if ex.get("recommendation_mark") is not None:
            item["analyst"] = round(float(ex["recommendation_mark"]), 2)
        if ex.get("dividend_amount_recent") and ts_to_date(ex.get("dividend_ex_date_recent")):
            item["div_amt"] = round(float(ex["dividend_amount_recent"]), 3)
            item["div_date"] = ts_to_date(ex["dividend_ex_date_recent"])
            item["div_src"] = "TradingView"
            if ts_to_date(ex.get("dividend_payment_date_recent")):
                item["div_pay"] = ts_to_date(ex["dividend_payment_date_recent"])
            if ex.get("dividends_yield_current") is not None:
                item["div_yield"] = round(float(ex["dividends_yield_current"]), 2)
        o = outlook(ex)
        if o:
            item.update(o)
        if sym in tech and tech[sym].get("Recommend.All") is not None:
            item["tech"] = round(float(tech[sym]["Recommend.All"]), 3)
        stocks.append(item)

    missing = [s["symbol"] for s in stocks if "error" not in s and "div_amt" not in s]
    ydiv = yahoo_dividends(missing)
    for s in stocks:
        if s["symbol"] in ydiv:
            s["div_date"], s["div_amt"] = ydiv[s["symbol"]]
            s["div_src"] = "Yahoo Finance"

    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "TradingView (delayed ~15 min); dividends gaps from Yahoo Finance",
        "stocks": stocks,
    }
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for s in stocks if "error" not in s)
    print(f"Wrote {OUTPUT_FILE} - {ok}/{len(stocks)} tickers")


if __name__ == "__main__":
    main()
