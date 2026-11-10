# Boardroom Terminal

A searchable map of who sits on which US public-company boards, and the shortest chain of shared board seats between any two companies or people.

All data comes from insider filings (Forms 3, 4 and 5) that directors file with the SEC, for companies listed on the NYSE, Nasdaq and Cboe.

## How it updates

`.github/workflows/update.yml` runs on the 2nd of each month:

1. `scripts/update.py` reads SEC's [insider transactions data sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets) page and keeps the newest 12 quarters (three years).
2. If SEC hasn't posted a new quarter since the last build, it stops with `NO CHANGE`. SEC publishes these files quarterly, so the site changes about four times a year.
3. Otherwise it rebuilds the director graph (`build_graph.py`), looks up industry codes for any new companies (`fetch_sic.py`, cached in `data/company_meta.json`) and writes `site/board_data.json` (`finalize.py`).
4. It refuses to publish if the new data is more than 10% smaller than the live data, which usually means SEC changed a file format.
5. The site in `site/` is deployed to GitHub Pages.

To force a rebuild, open the **Actions** tab, choose **Monthly data refresh**, press **Run workflow** and tick **force**.

## Setup

- Repository secret `SEC_USER_AGENT`: a name and contact email, for example `Jane Doe jane@example.com`. SEC's fair-access policy requires it on every download.
- Settings → Pages → Source: **GitHub Actions**.

## Run locally

```bash
SEC_USER_AGENT="Your Name you@example.com" python3 -I scripts/update.py --force
python3 -m http.server 8000 --directory site
```

`scripts/validate.py` spot-checks a sample of boards against each company's latest proxy statement.

## Limits

- A seat is "current" when the director filed for that company in the 15 months before the newest data. Older seats are hidden by default.
- Foreign companies that don't file these forms, private companies and nonprofits are not included.
- A shared board means two people served together. It does not mean either will make an introduction.
