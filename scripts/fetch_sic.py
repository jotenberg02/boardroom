"""Fetch SEC industry (SIC), state, and fund status for each company in the graph.

Usage: python3 -I fetch_sic.py <board_data.json> <out_json> [shard nshards]
Resumable: skips CIKs already in the output file. Stays under SEC's 10 req/s.
"""
import json, os, subprocess, sys, time

# SEC requires a contact in the User-Agent: "Name email@example.com".
UA = os.environ.get("SEC_USER_AGENT") or sys.exit("Set SEC_USER_AGENT to 'Name email' (SEC fair-access policy).")
data = json.load(open(sys.argv[1]))
out = sys.argv[2]
meta = json.load(open(out)) if os.path.exists(out) else {}

shard, nshards = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, 1)
todo = [c[0] for c in data["companies"] if str(c[0]) not in meta and c[0] % nshards == shard]
print("to fetch", len(todo), flush=True)
for i, cik in enumerate(todo):
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    try:
        j = json.loads(subprocess.run(
            ["curl", "-sSf", "--max-time", "30", "-A", UA, url],
            capture_output=True, check=True).stdout)
        ba = (j.get("addresses") or {}).get("business") or {}
        meta[str(cik)] = {
            "sic": j.get("sic") or "",
            "sicDesc": j.get("sicDescription") or "",
            "entityType": j.get("entityType") or "",
            "inc": j.get("stateOfIncorporation") or "",
            "city": (ba.get("city") or "").title(),
            "state": ba.get("stateOrCountry") or "",
            "website": j.get("website") or "",
            # Investment companies file N-CSR / N-CEN; operating companies don't.
            "fund": any(f in ("N-CSR", "N-CSRS", "N-CEN", "N-2") for f in j["filings"]["recent"]["form"][:400]),
        }
    except Exception as e:
        print("fail", cik, e, flush=True)
        time.sleep(2)
    time.sleep(0.3)
    if i % 50 == 0:
        json.dump(meta, open(out, "w"))
        print(i, flush=True)
json.dump(meta, open(out, "w"))
print("done", len(meta), flush=True)
