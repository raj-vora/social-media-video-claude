"""Pull 10+ years of daily closes, dividend and split events for the dividend-stock
universe from Yahoo Finance's public chart API, and cache the raw JSON.

Usage: python dividend-income-2026/data/fetch_dividends.py [--refresh]
Raw responses go to .cache/yahoo/<ticker>.json (gitignored); analyse.py reads them.
"""

import datetime as dt
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "yahoo"
UNIVERSE = pathlib.Path(__file__).with_name("universe.json")
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1={}&period2={}&interval=1d&events=div%7Csplit")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
START = dt.datetime(2014, 1, 1, tzinfo=dt.timezone.utc)


def fetch(ticker):
    end = int(time.time())
    req = urllib.request.Request(URL.format(ticker, int(START.timestamp()), end), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    tickers = [s["ticker"] for s in json.loads(UNIVERSE.read_text())]
    for t in tickers:
        out = CACHE / f"{t}.json"
        if out.exists() and "--refresh" not in sys.argv:
            continue
        try:
            out.write_text(json.dumps(fetch(t)))
            print("ok  ", t)
        except Exception as e:
            print("FAIL", t, e)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
