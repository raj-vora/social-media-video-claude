"""Gold numbers for the SGB vs Gold ETF series, from the Yahoo JSON that fetch_prices.py
caches in .cache/yahoo/ and from sgb_tranches.csv.

GOLDBEES (Nippon India ETF Gold BeES) stands in for the domestic gold price: it holds
physical gold in India, so it carries import duty, unlike COMEX gold x USD/INR. Its price
is also net of about 0.7-1% a year of expenses, so it slightly understates gold itself.

Writes, next to this file:
    sgb_returns.csv        every tranche: issue price, redemption (known) or value at
                           IBJA_TODAY, gain, coupon earned, gold-only and total return
    calendar_returns.csv   calendar-year price returns, GOLDBEES vs Nifty 50 (price only)
    analysis_summary.md    the headline figures the scripts quote
Usage: python gold-2026/data/analyse.py
"""

import csv
import datetime as dt
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "yahoo"
HERE = pathlib.Path(__file__).parent
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OZ = 31.1035

# IBJA 999 rate, Rs per gram, 2 Nov 2026 (sgbanalyzer.com/sgb-price-today, 10:26 am).
# Update this and re-run before the scripts are locked.
IBJA_TODAY = 13777
IBJA_DATE = dt.date(2026, 11, 2)

# Redemption prices (Rs per gram) collected so far. "final" = maturity at 8 years,
# "early" = premature exit window. Sources in README_methodology.md.
KNOWN_REDEMPTIONS = {
    "2015-16 Series I": ("final", dt.date(2023, 11, 30), 6132),
    "2017-18 Series XIV": ("final", dt.date(2026, 1, 1), 13486),
    "2018-19 Series II": ("final", dt.date(2026, 10, 23), 14425),   # blog-sourced, verify
    "2019-20 Series VI": ("early", dt.date(2026, 10, 30), 14213),
    "2020-21 Series III": ("early", dt.date(2026, 6, 16), 14774),
}


def load(ticker):
    res = json.loads((CACHE / f"{ticker}.json").read_text())["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    pts = sorted((dt.datetime.fromtimestamp(t, IST).date(), c)
                 for t, c in zip(res["timestamp"], closes) if c)
    # Yahoo leaves a few closes around the ETFs' 1:100 splits unadjusted (GOLDBEES: 0.34
    # between 33.6 and 33.7 in Dec 2019). Drop a close that is off by 2x from the median
    # of the five on either side of it.
    def ok(i):
        near = sorted(c for _, c in pts[max(0, i - 5):i] + pts[i + 1:i + 6])
        med = near[len(near) // 2]
        return med / 2 < pts[i][1] < med * 2
    return [p for i, p in enumerate(pts) if ok(i)]


def at(series, day):
    """Last close on or before day."""
    best = None
    for d, c in series:
        if d > day:
            break
        best = (d, c)
    return best


def cagr(v0, v1, years):
    return (v1 / v0) ** (1 / years) - 1


def years_between(a, b):
    return (b - a).days / 365.25


def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def drawdowns(series, min_fall=0.15):
    """Peak-to-trough falls of at least min_fall, with how long the recovery took."""
    out, peak, peak_d, trough, trough_d = [], series[0][1], series[0][0], None, None
    for d, c in series:
        if c >= peak:
            if trough is not None and 1 - trough / peak >= min_fall:
                out.append((peak_d, peak, trough_d, trough, d))
            peak, peak_d, trough, trough_d = c, d, None, None
        elif trough is None or c < trough:
            trough, trough_d = c, d
    if trough is not None and 1 - trough / peak >= min_fall:
        out.append((peak_d, peak, trough_d, trough, None))
    return out


def sgb_rows():
    rows = []
    with open(HERE / "sgb_tranches.csv", newline="") as f:
        for r in csv.DictReader(f):
            issue = dt.date.fromisoformat(r["issue_date"])
            price, coupon = int(r["issue_price"]), float(r["coupon_pct"]) / 100
            maturity = add_years(issue, 8)
            known = KNOWN_REDEMPTIONS.get(r["series"])
            if known:
                kind, end, value = known
            elif maturity <= IBJA_DATE:
                kind, end, value = "matured_unrecorded", maturity, None
            else:
                kind, end, value = "held_at_ibja", IBJA_DATE, IBJA_TODAY
            yrs = years_between(issue, end)
            row = {"series": r["series"], "issue_date": issue.isoformat(), "issue_price": price,
                   "maturity": maturity.isoformat(), "status": kind, "value_date": end.isoformat(),
                   "value": value or "", "years": round(yrs, 2)}
            if value:
                # Coupon is paid half-yearly on the issue price; count whole half-years.
                coupons = math.floor(yrs * 2 + 1e-6) * coupon / 2 * price
                row.update(gold_gain_pct=round((value / price - 1) * 100, 1),
                           coupon_earned=round(coupons),
                           total_multiple=round((value + coupons) / price, 2),
                           gold_cagr_pct=round(cagr(price, value, yrs) * 100, 1))
            rows.append(row)
    return rows


def main():
    gold_usd, fx, bees, nifty = load("GC=F"), load("INR=X"), load("GOLDBEES.NS"), load("^NSEI")
    sbi, kotak = load("SETFGOLD.NS"), load("GOLD1.NS")
    last = bees[-1][0]
    md = [f"# Gold series: headline numbers\n",
          f"Generated by `analyse.py` from Yahoo closes to {last} and IBJA Rs {IBJA_TODAY:,}/g "
          f"({IBJA_DATE}). GOLDBEES is the rupee gold proxy (price, after expenses).\n"]

    # 1. Trailing returns
    md.append("## Trailing price CAGR to " + last.isoformat() + "\n")
    md.append("| Years | Gold in Rs (GOLDBEES) | Gold in $ (COMEX) | Nifty 50 (price only) |")
    md.append("|---|---|---|---|")
    for n in (1, 3, 5, 10, 15):
        start = add_years(last, -n)
        cells = []
        for s in (bees, gold_usd, nifty):
            d0, v0 = at(s, start)
            cells.append(f"{cagr(v0, s[-1][1], years_between(d0, s[-1][0])) * 100:.1f}%")
        md.append(f"| {n} | " + " | ".join(cells) + " |")

    # 2. The 2026 peak and the fall since
    pk_d, pk = max(bees, key=lambda p: p[1])
    gpk_d, gpk = max(gold_usd, key=lambda p: p[1])
    md.append("\n## The 2026 peak\n")
    md.append(f"- GOLDBEES peak close {pk:.2f} on {pk_d}; now {bees[-1][1]:.2f} "
              f"({(bees[-1][1] / pk - 1) * 100:.1f}%). Rs 1 lakh at the peak is Rs "
              f"{100000 * bees[-1][1] / pk:,.0f} now.")
    md.append(f"- COMEX gold peak close ${gpk:,.0f} on {gpk_d}; now ${gold_usd[-1][1]:,.0f} "
              f"({(gold_usd[-1][1] / gpk - 1) * 100:.1f}%).")
    md.append(f"- USD/INR {at(fx, gpk_d)[1]:.2f} at the peak, {fx[-1][1]:.2f} now: the weaker rupee "
              "and the May 2026 duty rise cushioned the fall in rupees.")
    intl_now = gold_usd[-1][1] * fx[-1][1] / OZ
    md.append(f"- International gold in rupees now Rs {intl_now:,.0f}/g vs IBJA Rs {IBJA_TODAY:,}/g: "
              f"domestic premium {(IBJA_TODAY / intl_now - 1) * 100:.1f}% (duty, before GST).")

    # 3. Past drawdowns in rupees
    md.append("\n## Rupee gold falls of 15% or more since Jan 2009 (GOLDBEES closes)\n")
    md.append("| Peak | Trough | Fall | Back to the peak |")
    md.append("|---|---|---|---|")
    for p_d, p, t_d, t, rec in drawdowns(bees):
        back = f"{rec} ({years_between(p_d, rec):.1f} yrs after the peak)" if rec else "not yet"
        md.append(f"| {p_d} | {t_d} | {(t / p - 1) * 100:.0f}% | {back} |")

    # 4. Calendar years
    cal = []
    for y in range(2010, last.year + 1):
        row = {"year": y if y < last.year else f"{y} YTD"}
        for name, s in (("goldbees_pct", bees), ("nifty_pct", nifty), ("gold_usd_pct", gold_usd)):
            v0 = at(s, dt.date(y - 1, 12, 31))[1]
            v1 = at(s, dt.date(y, 12, 31))[1]
            row[name] = round((v1 / v0 - 1) * 100, 1)
        cal.append(row)
    with open(HERE / "calendar_returns.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cal[0]))
        w.writeheader()
        w.writerows(cal)
    gold_wins = sum(1 for r in cal if r["goldbees_pct"] > r["nifty_pct"])
    md.append(f"\n## Calendar years 2010-{last.year}\n")
    md.append(f"Gold beat the Nifty (price only) in {gold_wins} of {len(cal)} calendar years; "
              "see `calendar_returns.csv`.")

    # 5. Expense drag: three ETFs that hold the same thing
    md.append("\n## Same gold, different ETFs (10-year price CAGR)\n")
    start = add_years(last, -10)
    for name, s in (("Nippon GOLDBEES", bees), ("SBI SETFGOLD", sbi), ("Kotak GOLD1", kotak)):
        d0, v0 = at(s, start)
        md.append(f"- {name}: {cagr(v0, s[-1][1], years_between(d0, s[-1][0])) * 100:.2f}%")

    # 6. SGB vs ETF, first tranche, same eight years
    rows = sgb_rows()
    with open(HERE / "sgb_returns.csv", "w", newline="") as f:
        fields = list(rows[0]) + [k for k in ("gold_gain_pct", "coupon_earned", "total_multiple",
                                               "gold_cagr_pct") if k not in rows[0]]
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)
    first = rows[0]
    s, e = dt.date(2015, 11, 30), dt.date(2023, 11, 30)
    b0, b1 = at(bees, s)[1], at(bees, e)[1]
    n0, n1 = at(nifty, s)[1], at(nifty, e)[1]
    units = 100000 / first["issue_price"]
    md.append("\n## Rs 1 lakh on 30 Nov 2015, held 8 years (SGB 2015-16 Series I)\n")
    md.append(f"- SGB: {units:.1f} g, redeemed at Rs 6,132 = Rs {units * 6132:,.0f}, plus "
              f"Rs {units * first['coupon_earned']:,.0f} of interest (taxable at slab). "
              "Maturity gain tax-free.")
    md.append(f"- GOLDBEES: Rs {100000 * b1 / b0:,.0f} (capital gain taxable).")
    md.append(f"- Nifty 50 price only: Rs {100000 * n1 / n0:,.0f} (plus roughly 1.3% a year of dividends).")

    held = [r for r in rows if r["status"] == "held_at_ibja"]
    best = max((r for r in rows if r["value"]), key=lambda r: r["total_multiple"])
    worst = min(held, key=lambda r: r["total_multiple"])
    md.append("\n## SGB tranches\n")
    md.append(f"- {len(rows)} tranches, Nov 2015 to Feb 2024; {len(held)} still outstanding at "
              f"{IBJA_DATE} (matured ones without a recorded price are left blank).")
    md.append(f"- Best multiple: {best['series']} at {best['total_multiple']}x incl. interest "
              f"(issue Rs {best['issue_price']:,}, valued Rs {best['value']:,}).")
    md.append(f"- Weakest outstanding: {worst['series']} (issue Rs {worst['issue_price']:,}) "
              f"at {worst['total_multiple']}x, even after the 2026 fall.")
    upcoming = [r for r in rows if IBJA_DATE < dt.date.fromisoformat(r["maturity"])
                <= add_years(IBJA_DATE, 1)]
    md.append(f"- Maturing in the next 12 months: " +
              ", ".join(f"{r['series']} ({r['maturity']}, issued at Rs {r['issue_price']:,})"
                        for r in upcoming))

    (HERE / "analysis_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
