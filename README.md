# UFC Elo Ratings (UFC-only) — Quick README

Minimal pipeline to build a **clean fights table**, classify **method strength**, and run **Elo** over UFC bouts.

## Requirements

* Python **3.10+**
* `pandas`

  ```bash
  pip install -r requirements.txt
  ```

  `requirements.txt`:

  ```
  pandas>=2.0
  ```

## Files (inputs)

* `data/ufc_event_details.csv` — event → date
* `data/ufc_fight_results.csv` — bout, outcome, method, details
* `data/UFC_fighter_tott.csv` *(optional)* — maps fighter name → UFC Stats URL (stable ID)

> Output files go in `build/`.

## Run the pipeline (all steps)

### 1) Step 1 — Unify fights (clean + join + sort)

**With fighter URLs (preferred)**

```bash
python load_and_prepare.py \
  --events data/ufc_event_details.csv \
  --results data/ufc_fight_results.csv \
  --fighters data/UFC_fighter_tott.csv \
  -o build/fights_unified.csv
```

**Without fighter URLs**

```bash
python load_and_prepare.py \
  --events data/ufc_event_details.csv \
  --results data/ufc_fight_results.csv \
  -o build/fights_unified.csv
```

### 2) Step 2 — Classify method (finish / dominant decision / decision)

```bash
python classify_methods.py \
  -i build/fights_unified.csv \
  -o build/fights_classified.csv
```

(Optional multipliers)

```bash
python classify_methods.py \
  -i build/fights_unified.csv \
  -o build/fights_classified.csv \
  --m-finish 1.20 --m-dom 1.10 --m-dec 1.00
```

### 3) Step 3 — Elo updates

```bash
python elo_update.py \
  python elo_update.py \
  -i build/fights_classified.csv \
  --out-history build/elo_history.csv \
  --out-ratings build/elo_ratings_current.csv \
  --out-ratings-simple build/elo_ratings_simple.csv
```

(Optional params)

```bash
python elo_update.py \
  -i build/fights_classified.csv \
  --out-history build/elo_history.csv \
  --out-ratings build/elo_ratings_current.csv \
  --K 24 --scale 350 --base-rating 1500
```

## Outputs

* `build/fights_unified.csv` — cleaned, dated, UFC fights (A/B names, winner\_label, rounds\_scheduled, etc.)
* `build/fights_classified.csv` — adds `method_class`, `method_multiplier`, `decision_basis`, `judge_margins`
* `build/elo_history.csv` — per-fight Elo audit (pre/post ratings, win prob `p_A_win`, `K_eff`, etc.)
* `build/elo_ratings_current.csv` — latest rating per fighter + W/L/D and first/last UFC fight dates

## Notes

* Fights are processed **chronologically** (`DATE, EVENT, BOUT`).
* New fighters start at **1500**; update rule: `rating += K * method_multiplier * (S - P)`.
* Draws use `S=0.5`; **No Contests** are skipped.
* `UFC_fighter_tott.csv` is optional; if missing, IDs fall back to normalized names.

#### 3.1) Calculating peak Elo

```bash
python compute_peak_elo.py \
  -i build/elo_history.csv \
  -o build/elo_peak_ratings.csv \
  --out-simple build/elo_peak_ratings_simple.csv
```