"""Dividend metrics for every stock in universe.json, from the Yahoo JSON that
fetch_dividends.py caches in .cache/yahoo/.

Indian companies declare dividends per fiscal year (April-March), and interims slip
across calendar years, so annual sums here are by fiscal year of the ex-date:
FY2026 = 1 Apr 2025 - 31 Mar 2026.

Per stock:
    price, ttm_div, ttm_yield     latest close; dividends with ex-date in the last 365 days
    fy_divs                       per-share dividends by fiscal year (split-adjusted by Yahoo)
    paid_years                    of the 10 full fiscal years FY2017-FY2026, how many paid anything
    cuts                          full fiscal years whose dividend fell below 70% of the year before
    div_cagr_10y                  3-yr average FY2024-26 vs FY2015-17, annualised over 9 years
    lakh_*                        Rs 1,00,000 invested at the close nearest BASE_DATE, dividends
                                  taken as cash (not reinvested), pre-tax: what it is worth now,
                                  cash received so far, and income over the last 12 months
Usage: python dividend-income-2026/data/analyse.py [--json]   (writes stocks_metrics.json)
"""

import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "yahoo"
HERE = pathlib.Path(__file__).parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BASE_DATE = dt.date(2016, 10, 17)
FULL_FYS = list(range(2017, 2027))


def fy(d):
    return d.year + 1 if d.month >= 4 else d.year


def load(ticker):
    res = json.loads((CACHE / f"{ticker}.json").read_text())["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    day = lambda ts: dt.datetime.fromtimestamp(int(ts), IST).date()
    closes = [(day(t), c) for t, c, v in zip(res.get("timestamp", []), q["close"], q["volume"]) if c and v]
    divs = sorted((day(ts), e["amount"]) for ts, e in res.get("events", {}).get("dividends", {}).items())
    splits = sorted((str(day(ts)), e["splitRatio"]) for ts, e in res.get("events", {}).get("splits", {}).items())
    return closes, divs, splits


def close_on(closes, d):
    best = min(closes, key=lambda x: abs((x[0] - d).days))
    return best if abs((best[0] - d).days) <= 10 else None


def metrics(stock):
    closes, divs, splits = load(stock["ticker"])
    last_d, price = closes[-1]
    ttm = sum(a for d, a in divs if (last_d - d).days <= 365)
    fyd = defaultdict(float)
    for d, a in divs:
        fyd[fy(d)] += a
    paid = sum(1 for y in FULL_FYS if fyd[y] > 0)
    cuts = [y for y in FULL_FYS if fyd[y - 1] > 0 and fyd[y] < 0.7 * fyd[y - 1]]
    old = sum(fyd[y] for y in (2015, 2016, 2017)) / 3
    new = sum(fyd[y] for y in (2024, 2025, 2026)) / 3
    cagr = (new / old) ** (1 / 9) - 1 if old > 0 and new > 0 else None
    out = {**stock, "first_close": str(closes[0][0]), "last_date": str(last_d), "price": round(price, 2),
           "ttm_div": round(ttm, 2), "ttm_yield": round(ttm / price * 100, 2),
           "fy_divs": {y: round(fyd[y], 2) for y in range(2015, 2028)},
           "paid_years": paid, "cuts": cuts, "div_cagr_10y": None if cagr is None else round(cagr * 100, 1),
           "splits": splits}
    base = close_on(closes, BASE_DATE)
    if base:
        units = 100000 / base[1]
        cash = sum(a for d, a in divs if d > base[0]) * units
        out.update(base_date=str(base[0]), base_price=round(base[1], 2),
                   lakh_value=round(units * price), lakh_cash=round(cash),
                   lakh_total=round(units * price + cash), lakh_income_ttm=round(units * ttm),
                   price_cagr=round(((price / base[1]) ** (1 / ((last_d - base[0]).days / 365.25)) - 1) * 100, 1))
    return out


def main():
    rows = []
    for s in json.loads((HERE / "universe.json").read_text()):
        if (CACHE / f"{s['ticker']}.json").exists():
            try:
                rows.append(metrics(s))
            except Exception as e:
                print("skip", s["ticker"], e, file=sys.stderr)
    (HERE / "stocks_metrics.json").write_text(json.dumps(rows, indent=1))
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1))
        return
    rows.sort(key=lambda r: -r["ttm_yield"])
    print(f"{'symbol':12}{'price':>9}{'ttm':>7}{'yld%':>6}{'paid':>5}{'cuts':>14}{'dCAGR':>7}{'pCAGR':>7}{'1L->val':>9}{'cash':>8}{'inc/yr':>8}")
    for r in rows:
        print(f"{r['symbol']:12}{r['price']:9.1f}{r['ttm_div']:7.1f}{r['ttm_yield']:6.1f}{r['paid_years']:5}"
              f"{','.join(str(c)[2:] for c in r['cuts']):>14}{str(r['div_cagr_10y']):>7}{str(r.get('price_cagr')):>7}"
              f"{str(r.get('lakh_value')):>9}{str(r.get('lakh_cash')):>8}{str(r.get('lakh_income_ttm')):>8}")


if __name__ == "__main__":
    main()
