"""Spot-check graph directors against each company's latest proxy (DEF 14A).

Usage: python3 -I validate.py <board_data.json> <n_sample> <cache_dir>
Precision check: does each 'current' director's surname appear in the proxy?
Also prints how many 'possibly departed' directors still appear (stale-flag check).
"""
import html, json, os, random, re, subprocess, sys, time

# SEC requires a contact in the User-Agent: "Name email@example.com".
UA = os.environ.get("SEC_USER_AGENT") or sys.exit("Set SEC_USER_AGENT to 'Name email' (SEC fair-access policy).")
data = json.load(open(sys.argv[1]))
n = int(sys.argv[2])
cache = sys.argv[3]
os.makedirs(cache, exist_ok=True)


def get(url):
    time.sleep(0.2)
    return subprocess.run(
        ["curl", "-sSf", "--max-time", "60", "-A", UA, url],
        capture_output=True, check=True).stdout


C, P = data["companies"], data["people"]
by_co = {}
for s in data["seats"]:
    by_co.setdefault(s[1], []).append(s)
fundish = re.compile(r"\b(FUND|TRUST|INCOME|MUNI|PORTFOLIO)\b", re.I)
pool = [i for i, ss in by_co.items() if sum(s[4] for s in ss) >= 4 and not fundish.search(C[i][1])]
random.seed(7)
sample = random.sample(pool, n)

tot_cur = hit_cur = tot_old = hit_old = 0
for ci in sample:
    cik, name, ticker = C[ci][0], C[ci][1], C[ci][2]
    try:
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
        rec = sub["filings"]["recent"]
        k = next(i for i, f in enumerate(rec["form"]) if f == "DEF 14A")
        acc = rec["accessionNumber"][k].replace("-", "")
        doc = rec["primaryDocument"][k]
        fdate = rec["filingDate"][k]
        path = os.path.join(cache, f"{cik}.txt")
        if not os.path.exists(path):
            raw = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}").decode("utf-8", "replace")
            text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            open(path, "w").write(re.sub(r"\s+", " ", text))
        text = open(path).read().upper()
    except StopIteration:
        print(f"{ticker:6} no DEF 14A on file"); continue
    except Exception as e:
        print(f"{ticker:6} error {e}"); continue
    miss_cur, miss_old, c_cur, c_old = [], [], 0, 0
    for s in by_co[ci]:
        surname = P[s[0]][1].split()[-1].upper().rstrip(".")
        if surname in ("JR", "SR", "II", "III"):
            surname = P[s[0]][1].split()[-2].upper()
        found = re.search(r"\b" + re.escape(surname) + r"\b", text) is not None
        if s[4]:
            tot_cur += 1; hit_cur += found; c_cur += 1
            if not found: miss_cur.append(P[s[0]][1])
        else:
            tot_old += 1; hit_old += found; c_old += 1
            if found: miss_old.append(P[s[0]][1])
    print(f"{ticker:6} proxy {fdate} current {c_cur} not-in-proxy {miss_cur} | old {c_old} still-in-proxy {miss_old}")

print(f"\ncurrent directors found in proxy: {hit_cur}/{tot_cur}")
print(f"'possibly departed' still named in proxy: {hit_old}/{tot_old}")
