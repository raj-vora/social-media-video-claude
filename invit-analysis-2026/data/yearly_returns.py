"""Calendar-year price return and distribution yield for each retail top-5 InvIT,
from Yahoo Finance's public chart API (daily closes + dividend events).

For each full year Y:
    Price return %       = close(last trading day of Y) / close(last trading day of Y-1) - 1
    Distribution yield % = sum of distributions with an ex-date in Y / close(last trading day of Y-1)
    Total %              = price return + distribution yield (simple addition, as for 2026)
The first year of usable data is measured from its first traded close instead of the
prior year-end, and only counts distributions from that day on. A close only counts
as "traded" when that day's volume is above zero, and the series starts after the last
gap of more than 30 days between traded closes: Yahoo carries IRB InvIT Fund's price
forward unchanged, on zero volume, from mid-2017 until 18 May 2022, so its series
really starts on 19 May 2022.

2026 is left out on purpose: the 2026 YTD figures are the published ones in
invits_2026_returns.csv (baseline on/near 31 Dec 2025, latest ~20-22 Sep 2026).

Usage: python invit-analysis-2026/data/yearly_returns.py [--json]
"""

import datetime as dt
import json
import sys
import urllib.request
from collections import defaultdict

TICKERS = ["INDUSINVIT.BO", "PGINVIT.NS", "IRBINVIT.NS", "ROADSTAR.BO", "INDIGRID.NS"]
LAST_YEAR = 2025
MAX_GAP_DAYS = 30
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=1483228800&period2={}&interval=1d&events=div")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"


def fetch(ticker):
    end = int(dt.datetime(LAST_YEAR + 1, 1, 15, tzinfo=IST).timestamp())
    req = urllib.request.Request(URL.format(ticker, end), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["chart"]["result"][0]


def yearly(result):
    quote = result["indicators"]["quote"][0]
    day = lambda ts: dt.datetime.fromtimestamp(int(ts), IST).date()
    closes = [(day(t), c) for t, c, v in zip(result["timestamp"], quote["close"], quote["volume"])
              if c is not None and v]
    gaps = [i for i in range(1, len(closes)) if (closes[i][0] - closes[i - 1][0]).days > MAX_GAP_DAYS]
    if gaps:
        closes = closes[gaps[-1]:]
    start = closes[0][0]
    year_end, year_first = {}, {}
    for d, c in closes:
        year_end[d.year] = (d, c)
        year_first.setdefault(d.year, (d, c))
    dist = defaultdict(float)
    for ts, ev in result.get("events", {}).get("dividends", {}).items():
        if day(ts) > start:  # paid out before the first traded close isn't part of the return
            dist[day(ts).year] += ev["amount"]

    rows = []
    for y in sorted(y for y in year_end if y <= LAST_YEAR):
        base = year_end.get(y - 1) or year_first[y]
        price = (year_end[y][1] / base[1] - 1) * 100
        yld = dist[y] / base[1] * 100
        rows.append({
            "year": y, "partial": y - 1 not in year_end,
            "base_date": str(base[0]), "base": round(base[1], 2),
            "end_date": str(year_end[y][0]), "end": round(year_end[y][1], 2),
            "distributions": round(dist[y], 3),
            "price_pct": round(price, 2), "dist_pct": round(yld, 2), "total_pct": round(price + yld, 2),
        })
    return rows


def main():
    out = {t: yearly(fetch(t)) for t in TICKERS}
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
        return
    for t, rows in out.items():
        print(t)
        for r in rows:
            tag = " (partial, from " + r["base_date"] + ")" if r["partial"] else ""
            print(f"  {r['year']}{tag}: price {r['price_pct']:+.2f}%  distributions Rs.{r['distributions']:.3f}"
                  f" = {r['dist_pct']:.2f}%  total {r['total_pct']:+.2f}%")


if __name__ == "__main__":
    main()
