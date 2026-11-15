"""Cross-check Yahoo's dividend history against screener.in for the shortlist: top-ratio
box (market cap, price, dividend yield, ROE, ROCE) plus the annual P&L rows for EPS and
dividend payout %, from which dividend per share = EPS x payout. Pages are cached in
.cache/screener/. Writes screener_check.json.

Usage: python dividend-income-2026/data/screener_check.py SYMBOL [SYMBOL ...]
"""

import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "screener"
OUT = pathlib.Path(__file__).with_name("screener_check.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"


def get(url):
    for wait in (0, 30, 90):
        time.sleep(wait or 6)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise RuntimeError("still rate-limited")


def page(sym):
    """Consolidated figures, or standalone when the company files no consolidated accounts."""
    f = CACHE / f"{sym}.html"
    if not f.exists():
        base = f"https://www.screener.in/company/{urllib.parse.quote(sym)}/"
        doc = get(base + "consolidated/")
        if "Dividend Payout" not in doc:
            doc = get(base)
        f.write_text(doc)
    return f.read_text()


def num(s):
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse(doc):
    out = {}
    for name, val in re.findall(r'<span class="name">\s*(.*?)\s*</span>.*?<span class="number">([^<]*)</span>', doc, re.S):
        out[html.unescape(name)] = num(val)
    pl = doc[doc.find('id="profit-loss"'):]
    pl = pl[:pl.find("</table>")]
    years = re.findall(r"<th[^>]*>\s*(Mar \d{4}|TTM)\s*</th>", pl)
    rows = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", pl, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            label = html.unescape(cells[0]).replace("\xa0", "").replace("+", "").strip()
            rows[label] = dict(zip(years, map(num, cells[1:])))
    eps, pay = rows.get("EPS in Rs", {}), rows.get("Dividend Payout %", {})
    out["dps"] = {y: round(eps[y] * pay[y] / 100, 2) for y in pay if eps.get(y) is not None and pay[y] is not None}
    out["payout"] = pay
    out["eps"] = eps
    return out


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    for sym in sys.argv[1:]:
        try:
            data[sym] = parse(page(sym))
            d = data[sym]
            print(f"{sym:12} mcap {d.get('Market Cap')} price {d.get('Current Price')} yld {d.get('Dividend Yield')} "
                  f"ROE {d.get('ROE')} ROCE {d.get('ROCE')} | DPS " + " ".join(f"{k[-2:]}:{v}" for k, v in list(d['dps'].items())[-8:]))
        except Exception as e:
            print("FAIL", sym, e)
    OUT.write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    main()
