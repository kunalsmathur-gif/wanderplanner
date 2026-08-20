# Kaggle data runbook (Workstream B)

How to get a Kaggle-grounded India-domestic flight-fare data point into a
`scripts/ingest_kaggle_pricing.py` calibration proposal for
`core/distance_pricing.py`'s `DISTANCE_BANDS`. This is a **propose, don't
auto-apply** tool — same convention as `scripts/recalibrate_pricing.py` — a
human still reviews and pastes any resulting change by hand.

## 0. Who does what

- **Human, one-time:** create a free Kaggle account, generate an API
  credential, download the target dataset's CSV. See §1–§2.
- **Agent/script, repeatable:** everything from §3 onward — the ingestion
  script only ever reads an already-downloaded local CSV, it never talks to
  the Kaggle API itself. This keeps the `kaggle` package a dev-only tool,
  not a production dependency (see §4's rationale).

## 1. Account + credential

1. Sign up free at <https://www.kaggle.com>.
2. Go to <https://www.kaggle.com/settings/api> ("Account" tab used to host
   this before a Kaggle site redesign moved it — if a link is stale, search
   "API" from Settings).
3. Kaggle CLI 2.2.4 (current as of this runbook, confirmed live against
   real credentials for issue #55) resolves auth in this order — **lead
   with the access token**, it's the simplest and works headless/CI with no
   browser step:
   1. **Access token (recommended)** — click "Create New Token" on the API
      settings page for a token string, then either:
      - `export KAGGLE_API_TOKEN=<token>`, or
      - save it to `~/.kaggle/access_token` (`chmod 600`).
   2. **Legacy `kaggle.json`** — still supported, still works, but no
      longer the lead-recommended path. Download `kaggle.json` from the
      same settings page, place at `~/.kaggle/kaggle.json`, `chmod 600
      ~/.kaggle/kaggle.json`.
   3. **OAuth browser flow** — `kaggle auth login`, writes
      `~/.kaggle/credentials.json`. Needs a browser; skip for headless use.
   4. Anonymous — read-only public dataset listing, no downloads.

## 2. Corporate-network TLS gotcha (Netskope)

If Python's `requests`/`urllib3` (which the `kaggle` CLI/package uses)
fails with:

```
CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain
```

on a corporate network with Netskope TLS interception, this is **not** a
Kaggle-specific problem — `git`/`gh`/`curl` keep working because they read
the macOS system keychain, while Python's bundled `certifi` has no
corporate root and fails silently different from a network-down error.

Fix: merge `certifi`'s bundle with Netskope's local root certs
(`/Library/Application Support/Netskope/STAgent/data/nscacert.pem` and
`nstenantcert.pem`) into one file, then export it for the session:

```bash
export SSL_CERT_FILE=~/.certs/corp-ca-bundle.pem
export REQUESTS_CA_BUNDLE=~/.certs/corp-ca-bundle.pem
export CURL_CA_BUNDLE=~/.certs/corp-ca-bundle.pem
```

**Must be rebuilt after any `certifi` upgrade** (a `pip install -U
kaggle`/`certifi` silently reverts to the pre-merge bundle and the error
comes back). See this machine's `~/.certs/README.txt` for the rebuild
steps.

## 3. Install + download the dataset

`kaggle` is intentionally **not** in `apps/api/requirements.txt` — the
ingestion script (`scripts/ingest_kaggle_pricing.py`) only ever reads an
already-downloaded CSV, it never imports or shells out to the `kaggle`
package itself. Install it as a one-off dev tool for this download step
only:

```bash
pip install kaggle==2.2.4

# Primary dataset: India-domestic flight fares, CC0, EaseMyTrip, 6 metros.
kaggle datasets download -d shubhambathwal/flight-price-prediction -p /tmp/kaggle --unzip
```

**Verified live 2026-08-19** (this download was actually run, not just
researched): the current mirror unzips to three files, not the single
`Data_Train.csv` some older descriptions of this dataset reference:

- `economy.csv` (540,029 rows) — economy-class fares, **has a real journey
  `date` column** (`DD-MM-YYYY`, full March 2022), all 30 metro-pair
  directions. **This is the file `scripts/ingest_kaggle_pricing.py`
  targets** — it's the only one of the three with a usable date for the
  inflation/peak-multiplier calculation.
- `business.csv` (262,092 rows) — same shape, business-class fares. Out of
  scope for now — `DISTANCE_BANDS` models economy fares.
- `Clean_Dataset.csv` (300,154 rows) — combined economy+business with a
  `class` column but **no date column** (only a relative `days_left`), so
  it can't feed the peak-multiplier lookup as-is.

`economy.csv` columns: `date`, `airline`, `ch_code`, `num_code`,
`dep_time`, `from`, `time_taken`, `stop`, `arr_time`, `to`, `price` (the
`price` column uses a comma thousands separator, e.g. `"5,953"`). Cities
are the plain spellings (`Bangalore`, `Chennai`, `Delhi`, `Hyderabad`,
`Kolkata`, `Mumbai`) — this mirror does **not** have the `"Banglore"`
misspelling some older descriptions of this dataset mention, though the
ingestion script keeps that alias registered in case a different mirror
does.

## 4. Run the ingestion / calibration-proposal script

```bash
cd apps/api && .venv/bin/python -m scripts.ingest_kaggle_pricing \
    --csv-path /tmp/kaggle/economy.csv \
    --reference-year 2026
```

This groups fares by `core/distance_pricing.py`'s existing `DISTANCE_BANDS`
buckets (using haversine distance between the dataset's 6 known metro
cities), applies `core/pricing_multipliers.py`'s inflation multiplier for
dataset staleness (2022 → `--reference-year`), and prints a **JSON
calibration proposal** — median/p25/p75 inflation-adjusted round-trip fare
per band, alongside the current `DISTANCE_BANDS` figures, for a human to
compare side by side. It does **not** write to `core/distance_pricing.py`
— review the proposal, then hand-edit `DISTANCE_BANDS` (or better, feed the
proposed anchor into `scripts/recalibrate_pricing.py --band ... --round-trip-inr ...`
for a monotonicity-safe diff), same review discipline as every other
calibration tool in this repo.

Pass `--out proposal.json` to also save the JSON to a file.

### Sample live-run findings (2026-08-19)

Running the script above against the real `economy.csv` (233,774 rows
after skip-filters, in `short_domestic_hop`/`domestic_near_neighbour`/
`regional_international`, 0 in the two haul bands the dataset has no
distance coverage for) produced:

| band | current low–high (₹) | proposed p25 / median / p75 (₹, inflation-adjusted to 2026) |
|---|---|---|
| short_domestic_hop | 5,000–11,000 | 11,241 / 14,882 / 19,728 |
| domestic_near_neighbour | 12,000–30,000 | 10,507 / 14,572 / 19,119 |
| regional_international | 12,105–40,000 | 10,618 / 14,529 / 20,094 |
| long_haul | 44,422–90,232 | no data (dataset is India-domestic only) |
| ultra_long_haul | 55,000–110,000 | no data (dataset is India-domestic only) |

**Flag for the human reviewer, not resolved by this script:** the
domestic-metro-pair fares (all ~500–2000km) cluster around ₹14,500–15,000
regardless of distance band, which is why `domestic_near_neighbour` and
`regional_international`'s proposed medians come out *below* their current
low ends — real India-domestic fares don't scale with distance the way
`DISTANCE_BANDS` currently assumes for the international routes that
actually populate those two bands (SE Asia/Middle East regional, near-
neighbour international). Applying this proposal directly would
conflate domestic-metro pricing with the international routes those bands
are really meant for. Recommend treating this dataset as calibration
evidence for `short_domestic_hop` only (where it's a good fit) and
leaving `domestic_near_neighbour`/`regional_international` on their
existing international-route anchors, rather than a mechanical
"paste the median" apply.

## 5. Known gaps — do not treat these as solved by this runbook

- **India hotel pricing remains unresolved.** No clean free source exists
  (Kaggle India hotel listings are low-quality scraped snapshots with no
  usable price columns in practice — verified for `raj713335/tbo-hotels-dataset`,
  whose advertised "rates" don't actually exist in its 16-column schema).
  Continue the existing manual Numbeo/screenshot-anchor approach for India
  hotels — this is out of scope here, tracked separately (see
  `docs/data-freshness-strategy.md` for the long-term options).
- **No India-origin international-route dataset was found.** Those routes
  stay on the existing manually-anchored `DISTANCE_BANDS`; this runbook
  only helps calibrate the domestic/near-neighbour distance bands the
  Kaggle metro-pair data actually covers.
- **Don't trust a Kaggle dataset's description for its schema** — always
  verify actual column headers after download; several datasets on Kaggle
  advertise columns their CSV doesn't contain.
