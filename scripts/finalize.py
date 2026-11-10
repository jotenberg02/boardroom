"""Merge company metadata into the graph and write the app's data file.

Usage: python3 -I finalize.py <board_data.json> <company_meta.json> <out_json>
companies become: [cik, name, ticker, exchange, sicDesc, hqState, isFund]
"""
import json, re, sys
from collections import Counter

g = json.load(open(sys.argv[1]))
meta = json.load(open(sys.argv[2]))
FUND_SIC = {"6722", "6726"}
FUND_NAME = re.compile(r"\b(FUND|MUNI\w*|INCOME TRUST|MUNICIPAL)\b", re.I)

KEEP_UPPER = {"USA", "US", "AI", "REIT", "ETF", "LLC", "LP", "PLC", "NV", "SA", "AG", "SE", "II", "III", "IV", "BDC"}
SMALL = {"OF", "AND", "THE", "FOR", "IN", "ON", "AT", "DE"}


def tidy_company(name):
    """SEC names are often ALL CAPS ('TEXAS INSTRUMENTS INC'). Title-case those,
    keep short acronyms ('IBM', 'AT&T'), and drop state tags like '/DE/'."""
    name = re.sub(r"\s*/[A-Z]{2,3}/?\s*$", "", name).strip()
    if name != name.upper():
        return name
    out = []
    for i, w in enumerate(name.split()):
        core = w.strip(",.")
        if core in KEEP_UPPER or "&" in core or (len(core) <= 3 and core not in SMALL and core not in {"INC", "CO", "LTD", "CORP"}):
            out.append(w)
        elif core in SMALL and i:
            out.append(w.lower())
        else:
            out.append("-".join(p.capitalize() for p in w.split("-")))
    return " ".join(out)


missing = 0
comps = []
for cik, name, ticker, exch in g["companies"]:
    name = tidy_company(name)
    m = meta.get(str(cik))
    if m is None:
        missing += 1
        m = {}
    fund = bool(m.get("fund")) or m.get("sic") in FUND_SIC or (not m and bool(FUND_NAME.search(name)))
    sic = m.get("sicDesc", "").strip().title()
    comps.append([cik, name, ticker, exch, sic, m.get("state", ""), 1 if fund else 0])
g["companies"] = comps

cur = [s for s in g["seats"] if s[4] and not comps[s[1]][6]]
sec = Counter(comps[c][4] for c in {s[1] for s in cur} if comps[c][4])
g["sectors"] = sorted(([k, v] for k, v in sec.items() if v >= 3), key=lambda x: x[0])
json.dump(g, open(sys.argv[3], "w"), separators=(",", ":"))
print("missing meta", missing, "funds", sum(c[6] for c in comps), "sectors", len(g["sectors"]))
print("non-fund companies with current board", len({s[1] for s in cur}))
