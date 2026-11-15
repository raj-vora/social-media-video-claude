"""Apply the screen in README_methodology.md to stocks_metrics.json (Yahoo) and
screener_check.json (screener.in) and write top10.csv, ranked by current yield.

Screen: market cap >= Rs 10,000 cr; screener.in dividend yield >= 3%; dividend paid in
every fiscal year since listing (FY17-FY26, or since listing); no full fiscal year in
FY20-FY26 with a dividend below 70% of the year before (Yahoo, split-adjusted).
Usage: python dividend-income-2026/data/rank_top10.py   (run analyse.py + screener_check.py first)
"""

import csv
import json
import pathlib

HERE = pathlib.Path(__file__).parent
FY = range(2020, 2027)


def main():
    Y = {r["symbol"]: r for r in json.loads((HERE / "stocks_metrics.json").read_text())}
    S = json.loads((HERE / "screener_check.json").read_text())
    rows, dropped = [], []
    for sym, sc in S.items():
        y = Y[sym]
        d = {int(k): v for k, v in y["fy_divs"].items()}
        mcap, yld = sc.get("Market Cap"), sc.get("Dividend Yield")
        if not mcap or yld is None:
            dropped.append((sym, "no screener data")); continue
        cuts = [yr for yr in FY if d[yr - 1] > 0 and d[yr] < 0.7 * d[yr - 1]]
        first_fy = int(y["first_close"][:4]) + (1 if int(y["first_close"][5:7]) >= 4 else 0)
        missed = [yr for yr in range(max(2017, first_fy + 1), 2027) if d[yr] == 0]
        why = [w for ok, w in [(mcap >= 10000, "mcap<10k cr"), (yld >= 3, "yield<3%"),
                               (not cuts, f"cut FY{cuts}"), (len(missed) <= 1, f"missed FY{missed}")] if not ok]
        if why:
            dropped.append((sym, "; ".join(why))); continue
        rows.append({"symbol": sym, "name": y["name"], "sector": y["sector"], "price": y["price"],
                     "mcap_cr": mcap, "screener_yield_pct": yld, "yahoo_ttm_div": y["ttm_div"],
                     "missed_years": ",".join(map(str, missed)),
                     "dps_fy19": d[2019], "dps_fy26": d[2026],
                     "dps_cagr_7y_pct": round(((d[2026] / d[2019]) ** (1 / 7) - 1) * 100, 1) if d[2019] > 0 else "",
                     "roe": sc.get("ROE"), "roce": sc.get("ROCE"),
                     "lakh_base_date": y.get("base_date", ""), "lakh_value_now": y.get("lakh_value", ""),
                     "lakh_cash_received": y.get("lakh_cash", ""), "lakh_income_ttm": y.get("lakh_income_ttm", "")})
    rows.sort(key=lambda r: -r["screener_yield_pct"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    cols = ["rank"] + [c for c in rows[0] if c != "rank"]
    with open(HERE / "top10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r["rank"], r["symbol"], r["screener_yield_pct"], "missed", r["missed_years"], "cagr", r["dps_cagr_7y_pct"], "1L:", r["lakh_value_now"], r["lakh_cash_received"], r["lakh_income_ttm"])
    print("dropped:", *[f"{s}({w})" for s, w in dropped], sep="\n  ")


if __name__ == "__main__":
    main()
