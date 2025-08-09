# elo_update.py
# Step 3: Apply Elo updates over UFC fights (UFC-only), using method multipliers from Step 2.

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import math
import sys
import re
import pandas as pd

SPACE_RE = re.compile(r"\s+")

def norm(s: str) -> str:
    if pd.isna(s):
        return ""
    return SPACE_RE.sub(" ", str(s).strip())

def key_from_name(name: str) -> str:
    return norm(name).lower()

def logistic_prob(ra: float, rb: float, scale: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / scale))

@dataclass
class EloConfig:
    base_rating: float = 1500.0
    K: float = 24.0
    scale: float = 350.0

def choose_fighter_id(row, side: str) -> tuple[str, str]:
    if side == "a":
        url_col, name_col = "fighter_a_url", "fighter_a_name"
    else:
        url_col, name_col = "fighter_b_url", "fighter_b_name"
    name = norm(row.get(name_col, ""))
    url = norm(row.get(url_col, ""))
    fid = url if url else key_from_name(name)
    return fid, name

def outcome_scores(winner_label: str):
    w = (winner_label or "").strip().lower()
    if w == "a": return 1.0, 0.0
    if w == "b": return 0.0, 1.0
    if w == "draw": return 0.5, 0.5
    if w in ("nc", "unknown", ""): return None
    return None

def run_elo(input_csv: Path, out_hist: Path, out_ratings: Path, out_ratings_simple: Path, cfg: EloConfig):
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        print(f"[ERROR] Failed to read {input_csv}: {e}", file=sys.stderr)
        sys.exit(1)

    req = ["DATE","EVENT","BOUT","fighter_a_name","fighter_b_name","winner_label","method_class","method_multiplier"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        print(f"[ERROR] Input missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df = df.sort_values(["DATE","EVENT","BOUT"], kind="stable").reset_index(drop=True)

    ratings = defaultdict(lambda: cfg.base_rating)
    names, fights_ct, wins_ct, losses_ct, draws_ct = {}, defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    first_date, last_date = {}, {}

    history_rows = []

    for _, row in df.iterrows():
        scores = outcome_scores(str(row.get("winner_label","")))
        if scores is None:
            continue

        fid_a, name_a = choose_fighter_id(row, "a")
        fid_b, name_b = choose_fighter_id(row, "b")
        names[fid_a], names[fid_b] = name_a or fid_a, name_b or fid_b

        ra, rb = float(ratings[fid_a]), float(ratings[fid_b])

        m = row.get("method_multiplier", 1.0)
        try: m = float(m); 
        except: m = 1.0
        if not math.isfinite(m): m = 1.0

        p_a = logistic_prob(ra, rb, cfg.scale)
        s_a, s_b = scores
        k_eff = cfg.K * m

        ra_new = ra + k_eff * (s_a - p_a)
        rb_new = rb + k_eff * (s_b - (1.0 - p_a))
        ratings[fid_a], ratings[fid_b] = ra_new, rb_new

        fights_ct[fid_a] += 1; fights_ct[fid_b] += 1
        if s_a == 1.0: wins_ct[fid_a] += 1; losses_ct[fid_b] += 1
        elif s_b == 1.0: wins_ct[fid_b] += 1; losses_ct[fid_a] += 1
        else: draws_ct[fid_a] += 1; draws_ct[fid_b] += 1

        d = row.get("DATE")
        for fid in (fid_a, fid_b):
            if fid not in first_date or (pd.notna(d) and (pd.isna(first_date[fid]) or d < first_date[fid])): first_date[fid] = d
            if fid not in last_date  or (pd.notna(d) and (pd.isna(last_date[fid])  or d > last_date[fid])):  last_date[fid]  = d

        history_rows.append({
            "DATE": row.get("DATE"),
            "EVENT": norm(row.get("EVENT")),
            "BOUT": norm(row.get("BOUT")),
            "fighter_a_id": fid_a, "fighter_b_id": fid_b,
            "fighter_a_name": names[fid_a], "fighter_b_name": names[fid_b],
            "pre_rating_a": ra, "pre_rating_b": rb, "p_A_win": p_a,
            "winner_label": str(row.get("winner_label","")).strip().lower(),
            "method_class": norm(row.get("method_class")), "method_multiplier": m, "K_eff": k_eff,
            "rounds_scheduled": row.get("rounds_scheduled"),
            "WEIGHTCLASS": norm(row.get("WEIGHTCLASS")) if "WEIGHTCLASS" in df.columns else "",
            "METHOD": norm(row.get("METHOD")) if "METHOD" in df.columns else "",
            "REFEREE": norm(row.get("REFEREE")) if "REFEREE" in df.columns else "",
            "URL": norm(row.get("URL")) if "URL" in df.columns else "",
            "post_rating_a": ra_new, "post_rating_b": rb_new,
        })

    # Write history
    hist_df = pd.DataFrame(history_rows)
    out_hist.parent.mkdir(parents=True, exist_ok=True)
    hist_df.to_csv(out_hist, index=False)

    # Full ratings snapshot
    rows = []
    for fid, r in ratings.items():
        rows.append({
            "fighter_id": fid,
            "fighter_name": names.get(fid, fid),
            "rating": float(r),
            "fights": fights_ct.get(fid, 0),
            "wins": wins_ct.get(fid, 0),
            "losses": losses_ct.get(fid, 0),
            "draws": draws_ct.get(fid, 0),
            "first_date": first_date.get(fid),
            "last_date": last_date.get(fid),
        })
    rat_df = pd.DataFrame(rows).sort_values("rating", ascending=False).reset_index(drop=True)
    rat_df.to_csv(out_ratings, index=False)

    # Simple two-column export (name, rating)
    simple_df = rat_df[["fighter_name", "rating"]].copy()
    simple_df.to_csv(out_ratings_simple, index=False)

    print(f"[OK] Processed {len(hist_df)} fights. "
          f"Wrote: {out_hist.name}, {out_ratings.name}, {out_ratings_simple.name}")

def main():
    p = argparse.ArgumentParser(description="Step 3: Run Elo updates over UFC fights.")
    p.add_argument("-i", "--input", type=Path, required=True,
                   help="Input CSV from Step 2 (build/fights_classified.csv)")
    p.add_argument("--out-history", type=Path, default=Path("../build/elo_history.csv"),
                   help="Output CSV: per-fight Elo audit log")
    p.add_argument("--out-ratings", type=Path, default=Path("../build/elo_ratings_current.csv"),
                   help="Output CSV: latest ratings snapshot")
    p.add_argument("--out-ratings-simple", type=Path, default=Path("../build/elo_ratings_simple.csv"),
                   help="Output CSV: fighter_name,rating only")
    p.add_argument("--base-rating", type=float, default=1500.0)
    p.add_argument("--K", type=float, default=24.0)
    p.add_argument("--scale", type=float, default=350.0)
    args = p.parse_args()

    cfg = EloConfig(base_rating=args.base_rating, K=args.K, scale=args.scale)
    run_elo(args.input, args.out_history, args.out_ratings, args.out_ratings_simple, cfg)

if __name__ == "__main__":
    main()
