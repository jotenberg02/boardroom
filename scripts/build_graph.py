"""Build a director <-> company graph from SEC Form 3/4/5 bulk data sets.

Usage: python3 -I build_graph.py <secdata_dir> <out_json>

Input: unzipped quarterly folders (e.g. 2025q1/) holding SUBMISSION.tsv and
REPORTINGOWNER.tsv, plus tickers_exchange.json (SEC company_tickers_exchange).
Output: compact JSON with companies, people, and board seats.
"""
import csv, json, os, re, sys
from datetime import datetime

src, out = sys.argv[1], sys.argv[2]
csv.field_size_limit(10**8)

LISTED = {"NYSE", "Nasdaq", "CBOE"}
# Current = filed on this board within ~15 months of the newest data.
# Directors get annual equity grants, so a sitting director files at least yearly.
CURRENT_DAYS = 455

# Reporting owners flagged "Director" are sometimes funds that hold a board
# seat by deputization. Keep people only.
ENTITY = re.compile(
    r"\b(LLC|L\.L\.C|LP|L\.P|LTD|INC|CORP|CORPORATION|FUND|FUNDS|PARTNERS|"
    r"CAPITAL|HOLDINGS|TRUST|MANAGEMENT|ADVISORS|INVESTMENTS|VENTURES|GROUP|"
    r"COMPANY|PLC|AG|SA|GMBH|BANK|FOUNDATION|ASSOCIATES|EQUITY|LIMITED)\b",
    re.I,
)
SUFFIX = {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "MD", "PHD", "M.D.", "PH.D."}

tick = json.load(open(os.path.join(src, "tickers_exchange.json")))
listed = {}  # cik -> (name, ticker, exchange); first ticker wins (common stock)
for cik, name, ticker, exch in tick["data"]:
    if exch in LISTED and cik not in listed:
        listed[cik] = (name, ticker, exch)


def cap_word(w):
    """Capitalize a name word, including after hyphens/apostrophes and Mc."""
    if w.upper() in ("II", "III", "IV"):
        return w.upper()
    w = "".join(p.capitalize() for p in re.split(r"([-'])", w.lower()))
    if w.startswith("Mc") and len(w) > 2:
        w = "Mc" + w[2].upper() + w[3:]
    return w


def display_name(raw):
    """SEC stores 'LAST FIRST MIDDLE'. Return 'First Middle Last'."""
    parts = raw.replace(",", " ").split()
    if len(parts) < 2:
        return " ".join(cap_word(w) for w in parts)
    suffix = [p for p in parts[1:] if p.upper() in SUFFIX]
    given = [p for p in parts[1:] if p.upper() not in SUFFIX]
    return " ".join(cap_word(w) for w in given + [parts[0]] + suffix)


def d(s):
    return datetime.strptime(s, "%d-%b-%Y").date()


seats = {}    # (pcik, ccik) -> dict
people = {}   # pcik -> dict
companies = {}

for q in sorted(os.listdir(src)):
    sub_p = os.path.join(src, q, "SUBMISSION.tsv")
    own_p = os.path.join(src, q, "REPORTINGOWNER.tsv")
    if not os.path.exists(sub_p):
        continue
    subs = {}
    with open(sub_p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            subs[r["ACCESSION_NUMBER"]] = r
    with open(own_p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rel = r["RPTOWNER_RELATIONSHIP"] or ""
            # Insiders often drop the Director flag on later filings (a chair/CEO
            # files as "Officer"), so track every filing and keep pairs that
            # were flagged Director at least once.
            if not any(x in rel for x in ("Director", "Officer")):
                continue
            s = subs.get(r["ACCESSION_NUMBER"])
            if not s:
                continue
            ccik = int(s["ISSUERCIK"])
            if ccik not in listed:
                continue
            raw = r["RPTOWNERNAME"].strip()
            if ENTITY.search(raw):
                continue
            pcik = int(r["RPTOWNERCIK"])
            fd = d(s["FILING_DATE"])
            key = (pcik, ccik)
            st = seats.get(key)
            if st is None:
                st = seats[key] = {"first": fd, "last": fd, "officer": "Officer" in rel,
                                   "title": r["RPTOWNER_TITLE"].strip() if "Officer" in rel else "", "dir": False}
            if "Director" in rel:
                st["dir"] = True
            st["first"] = min(st["first"], fd)
            # Executive status and title come from the latest filing only, so a
            # former CEO who stays on as a director isn't tagged as an executive.
            if fd > st["last"] or (fd == st["last"] and not st["officer"]):
                st["officer"] = "Officer" in rel
                st["title"] = r["RPTOWNER_TITLE"].strip() if "Officer" in rel else ""
            st["last"] = max(st["last"], fd)
            p = people.get(pcik)
            if p is None or fd >= p["seen"]:
                people[pcik] = {
                    "name": display_name(raw),
                    "raw": raw,
                    "seen": fd,
                }

seats = {k: v for k, v in seats.items() if v["dir"]}
keep_p = {k[0] for k in seats}
people = {p: v for p, v in people.items() if p in keep_p}
companies = {k[1]: listed[k[1]] for k in seats}

newest = max(s["last"] for s in seats.values())
pids = sorted(people)
cids = sorted(companies)
pix = {c: i for i, c in enumerate(pids)}
cix = {c: i for i, c in enumerate(cids)}
seat_rows = []
for (pc, cc), s in seats.items():
    current = (newest - s["last"]).days <= CURRENT_DAYS
    seat_rows.append([
        pix[pc], cix[cc], s["first"].isoformat(), s["last"].isoformat(),
        1 if current else 0, 1 if s["officer"] else 0, s["title"],
    ])

data = {
    "asof": newest.isoformat(),
    "window": [min(s["first"] for s in seats.values()).isoformat(), newest.isoformat()],
    "companies": [[c, *companies[c]] for c in cids],          # cik, name, ticker, exchange
    "people": [[c, people[c]["name"]] for c in pids],  # cik, name (no addresses: some are homes)
    "seats": seat_rows,  # person_idx, company_idx, first, last, current, officer, title
}
with open(out, "w") as f:
    json.dump(data, f, separators=(",", ":"))

cur = [r for r in seat_rows if r[4]]
from collections import Counter
per_person = Counter(r[0] for r in cur)
per_co = Counter(r[1] for r in cur)
print("companies", len(cids), "people", len(pids), "seats", len(seat_rows), "current seats", len(cur))
print("companies w/ current board", len(per_co), "median board size", sorted(per_co.values())[len(per_co) // 2])
print("people on 2+ current boards", sum(1 for v in per_person.values() if v >= 2))
print("people on 3+ current boards", sum(1 for v in per_person.values() if v >= 3))
print("asof", newest, "bytes", os.path.getsize(out))
