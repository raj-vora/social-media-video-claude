"""Pull daily closes since 2008 for international gold, USD/INR, the larger NSE gold ETFs
and the Nifty from Yahoo Finance's public chart API, and cache the raw JSON.

Usage: python gold-2026/data/fetch_prices.py [--refresh]
Raw responses go to .cache/yahoo/<ticker>.json (gitignored); analyse.py reads them.
"""

import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "yahoo"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1={}&period2={}&interval=1d&events=div%7Csplit")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
START = dt.datetime(2008, 1, 1, tzinfo=dt.timezone.utc)
TICKERS = [
    "GC=F",          # COMEX gold futures, USD/oz (continuous front month)
    "INR=X",         # USD/INR
    "GOLDBEES.NS",   # Nippon India ETF Gold BeES (Mar 2007, the oldest and largest)
    "SETFGOLD.NS",   # SBI Gold ETF
    "GOLD1.NS",      # Kotak Gold ETF
    "HDFCGOLD.NS",   # HDFC Gold ETF (Yahoo history only from Jun 2023)
    "GOLDIETF.NS",   # ICICI Prudential Gold ETF (Yahoo history only from Dec 2023)
    "^NSEI",         # Nifty 50, price only
]


def fetch(ticker):
    end = int(time.time())
    req = urllib.request.Request(URL.format(urllib.parse.quote(ticker), int(START.timestamp()), end),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    for t in TICKERS:
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
