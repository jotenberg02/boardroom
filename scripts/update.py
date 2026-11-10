"""Monthly refresh: pull the latest SEC insider data and rebuild site/board_data.json.

Usage: SEC_USER_AGENT="Name email" python3 -I scripts/update.py [--force]

Steps:
  1. Read SEC's insider-transactions data set page; keep the newest QUARTERS files.
  2. Download any quarter not already in the work folder (plus the ticker/exchange map).
  3. Rebuild the director graph, fetch industry codes for new companies only
     (cached in data/company_meta.json), and write the app data file.
  4. Refuse to publish if the new data shrank sharply versus the live file.
Exit code 0 with "NO CHANGE" when SEC hasn't posted a new quarter (unless --force).
"""
import json, os, re, shutil, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")              # downloads + intermediate graph (gitignored)
SITE_DATA = os.path.join(ROOT, "site", "board_data.json")
META = os.path.join(ROOT, "data", "company_meta.json")
QUARTERS = 12                                   # three years of filings
MAX_SHRINK = 0.10                               # block publish if companies/seats drop >10%
UA = os.environ.get("SEC_USER_AGENT") or sys.exit("Set SEC_USER_AGENT to 'Name email' (SEC fair-access policy).")
PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def curl(url, out=None):
    cmd = ["curl", "-sSfL", "--retry", "3", "--max-time", "300", "-A", UA, url]
    if out:
        cmd += ["-o", out]
    r = subprocess.run(cmd, capture_output=True, check=True)
    return r.stdout


def run(*args):
    print("+", " ".join(args[1:]), flush=True)
    subprocess.run([sys.executable, "-I", *args], check=True)


os.makedirs(WORK, exist_ok=True)
sec_dir = os.path.join(WORK, "secdata")
os.makedirs(sec_dir, exist_ok=True)

# 1. Which quarters exist? (SEC has moved these files between paths, so read the page.)
html = curl(PAGE).decode("utf-8", "replace")
links = sorted(set(re.findall(r'href="(/files/[^"]*?(\d{4}q\d)_form345\.zip)"', html)), key=lambda x: x[1])
if len(links) < QUARTERS:
    sys.exit(f"Only found {len(links)} quarterly files on the SEC page; page layout may have changed.")
want = links[-QUARTERS:]
want_q = {q for _, q in want}
print("quarters:", want[0][1], "to", want[-1][1], flush=True)

# 2. Download missing quarters; drop ones that fell out of the window.
for d in os.listdir(sec_dir):
    if re.fullmatch(r"\d{4}q\d", d) and d not in want_q:
        shutil.rmtree(os.path.join(sec_dir, d))
new = []
for path, q in want:
    qdir = os.path.join(sec_dir, q)
    if os.path.exists(os.path.join(qdir, "REPORTINGOWNER.tsv")):
        continue
    z = os.path.join(sec_dir, q + ".zip")
    print("download", q, flush=True)
    curl("https://www.sec.gov" + path, z)
    with zipfile.ZipFile(z) as f:
        f.extractall(qdir)
    os.remove(z)
    new.append(q)
curl("https://www.sec.gov/files/company_tickers_exchange.json", os.path.join(sec_dir, "tickers_exchange.json"))

live = json.load(open(SITE_DATA)) if os.path.exists(SITE_DATA) else None
newest_q = want[-1][1]
if live and live.get("quarter") == newest_q and "--force" not in sys.argv:
    print(f"NO CHANGE: site already built from {newest_q}.")
    sys.exit(0)

# 3. Rebuild.
graph = os.path.join(WORK, "graph.json")
out = os.path.join(WORK, "board_data.json")
run(os.path.join(ROOT, "scripts", "build_graph.py"), sec_dir, graph)
os.makedirs(os.path.dirname(META), exist_ok=True)
run(os.path.join(ROOT, "scripts", "fetch_sic.py"), graph, META)
run(os.path.join(ROOT, "scripts", "finalize.py"), graph, META, out)

d = json.load(open(out))
d["quarter"] = newest_q
json.dump(d, open(out, "w"), separators=(",", ":"))

# 4. Sanity checks before publishing.
n_co, n_seat = len(d["companies"]), sum(1 for s in d["seats"] if s[4])
print(f"new data: {n_co} companies, {n_seat} current seats, as of {d['asof']}", flush=True)
if n_co < 3000 or n_seat < 25000:
    sys.exit("BLOCKED: new data is far smaller than expected; not publishing.")
if live:
    o_co, o_seat = len(live["companies"]), sum(1 for s in live["seats"] if s[4])
    if n_co < o_co * (1 - MAX_SHRINK) or n_seat < o_seat * (1 - MAX_SHRINK):
        sys.exit(f"BLOCKED: data shrank ({o_co}->{n_co} companies, {o_seat}->{n_seat} seats); not publishing.")
shutil.copy(out, SITE_DATA)
print(f"UPDATED: site data now built from {newest_q}.")
