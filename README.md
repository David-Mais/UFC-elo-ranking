# UFC Elo Ratings — Step 1 (Data Unification)

This repo (so far) loads your **UFC-only** CSV exports, cleans them, and produces a single, time-ordered fights table we’ll use for Elo updates in the next step.

## What this step does

* Reads:

  * `ufc_event_details.csv` (event dates)
  * `ufc_fight_results.csv` (who fought, who won, method, judges detail)
  * `UFC_fighter_tott.csv` *(optional)* for stable fighter IDs via UFC Stats profile URLs
* Cleans bout strings and fighter names.
* Infers the winner/loser from the `OUTCOME` column.
* Derives scheduled rounds (3 vs 5) from `TIME FORMAT`.
* Outputs `build/fights_unified.csv` sorted by date.

---

## Requirements

* Python **3.10+**
* Packages: `pandas`
  Install with:

  ```bash
  pip install -r requirements.txt
  ```
---

## Project layout (suggested)

```
.
├── data/
│   ├── ufc_event_details.csv
│   ├── ufc_fight_results.csv
│   └── UFC_fighter_tott.csv   # optional
├── build/                     # created by the script
├── load_and_prepare.py
├── requirements.txt
└── README.md
```

---

## Run Step 1

### With fighter URLs (preferred)

```bash
python load_and_prepare.py \
  --events data/ufc_event_details.csv \
  --results data/ufc_fight_results.csv \
  --fighters data/UFC_fighter_tott.csv \
  -o build/fights_unified.csv
```

### Without fighter URLs

```bash
python load_and_prepare.py \
  --events data/ufc_event_details.csv \
  --results data/ufc_fight_results.csv \
  -o build/fights_unified.csv
```

If all goes well:

```
[OK] Wrote N rows to build/fights_unified.csv
```

---

## Output: `build/fights_unified.csv`

Columns (ordered):

```
DATE, EVENT, BOUT,
fighter_a_name, fighter_b_name,
winner_label,                 # 'A' | 'B' | 'draw' | 'nc' | 'unknown'
WEIGHTCLASS, METHOD, decision_type,  # quick tag: unanimous/split/majority/other
ROUND, TIME, TIME FORMAT, REFEREE, DETAILS, URL,
rounds_scheduled,             # 3 or 5 (derived)
fighter_a_url, fighter_b_url  # only when fighters file provided
```

Notes:

* `winner_label` is derived from `OUTCOME`:

  * `W/L` → left name (A) won
  * `L/W` → right name (B) won
  * contains `D/D`/`DRAW` → draw
  * contains `NC`/`N/C` → no contest
* `decision_type` is a **rough** label from `METHOD`. We’ll refine dominance in Step 2.

# Step 2 — Classify Methods (Finish vs Dominant Decision vs Decision)

Run after you’ve created `build/fights_unified.csv` from Step 1.

## Quick start

```bash
python classify_methods.py \
  -i build/fights_unified.csv \
  -o build/fights_classified.csv
```

## With custom multipliers (optional)

```bash
python classify_methods.py \
  -i build/fights_unified.csv \
  -o build/fights_classified.csv \
  --m-finish 1.20 \
  --m-dom 1.10 \
  --m-dec 1.00
```

## Input / Output

* **Input:** `build/fights_unified.csv` (from Step 1)
* **Output:** `build/fights_classified.csv` with added columns:

  * `method_class` (`finish`, `decision_dominant`, `decision_normal`, `draw`, `nc`, `other`)
  * `method_multiplier` (numeric)
  * `decision_basis` (why it was classified that way)
  * `judge_margins` (parsed from `DETAILS`, if available)