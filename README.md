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

Got it — here’s your updated README rewritten so it matches your **new CLI workflow**, removes the old multi-script calls, and clearly explains single-command and step-by-step usage.

---

# UFC Elo Ratings (UFC-only) — Quick README

Minimal pipeline to build a **clean fights table**, classify **method strength**, and run **Elo** over UFC bouts — now with a single CLI interface.

---

## Requirements

* Python **3.10+**
* `pandas` (and optionally `PyYAML` if you use a config file)

```bash
pip install pandas pyyaml
```

---

## Files (inputs)

* `data/ufc_event_details.csv` — event → date
* `data/ufc_fight_results.csv` — bout, outcome, method, details
* `data/UFC_fighter_tott.csv` *(optional)* — maps fighter name → UFC Stats URL (stable ID)

> Output files go in the `build/` folder (relative to the project root).

---

## Running the pipeline

### **Option 1 — Full pipeline in one command**

From inside the `elo_calculator/` folder:

```bash
python ufcelo_cli.py run-all \
  --events ../data/ufc_event_details.csv \
  --results ../data/ufc_fight_results.csv \
  --fighters ../data/UFC_fighter_tott.csv
```

Optional parameters:

```bash
python ufcelo_cli.py run-all \
  --events ../data/ufc_event_details.csv \
  --results ../data/ufc_fight_results.csv \
  --m-finish 1.20 --m-dom 1.10 --m-dec 1.00 \
  --K 24 --scale 350 --base-rating 1500
```

---

### **Option 2 — Step-by-step**

#### 1) Prepare (unify fights)

```bash
python ufcelo_cli.py prepare \
  --events ../data/ufc_event_details.csv \
  --results ../data/ufc_fight_results.csv \
  --fighters ../data/UFC_fighter_tott.csv \
  -o ../build/fights_unified.csv
```

#### 2) Classify method (finish / dominant decision / decision)

```bash
python ufcelo_cli.py classify \
  -i ../build/fights_unified.csv \
  -o ../build/fights_classified.csv \
  --m-finish 1.20 --m-dom 1.10 --m-dec 1.00
```

#### 3) Elo updates

```bash
python ufcelo_cli.py elo \
  -i ../build/fights_classified.csv \
  --out-history ../build/elo_history.csv \
  --out-ratings ../build/elo_ratings_current.csv \
  --out-ratings-simple ../build/elo_ratings_simple.csv \
  --K 24 --scale 350 --base-rating 1500
```

#### 4) Peak Elo

```bash
python ufcelo_cli.py peak \
  -i ../build/elo_history.csv \
  -o ../build/elo_peak_ratings.csv \
  --out-simple ../build/elo_peak_ratings_simple.csv
```

---

## Outputs

* `build/fights_unified.csv` — cleaned, dated UFC fights (A/B names, winner\_label, rounds\_scheduled, etc.)
* `build/fights_classified.csv` — adds `method_class`, `method_multiplier`, `decision_basis`, `judge_margins`
* `build/elo_history.csv` — per-fight Elo audit (pre/post ratings, win prob `p_A_win`, `K_eff`, etc.)
* `build/elo_ratings_current.csv` — latest rating per fighter + W/L/D and first/last UFC fight dates
* `build/elo_ratings_simple.csv` — simplified latest ratings
* `build/elo_peak_ratings.csv` — peak rating per fighter
* `build/elo_peak_ratings_simple.csv` — simplified peak ratings

---

## Notes

* Fights are processed **chronologically** (`DATE, EVENT, BOUT`).
* New fighters start at **1500**; update rule:
  `rating += K * method_multiplier * (S - P)`
* Draws use `S=0.5`; **No Contests** are skipped.
* `UFC_fighter_tott.csv` is optional; if missing, IDs fall back to normalized names.