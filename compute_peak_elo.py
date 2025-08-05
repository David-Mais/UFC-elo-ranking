# compute_peak_elo.py
# Step 3.1: Compute each fighter's peak (highest) Elo rating from elo_history.csv,
# and also write a simple two-column file: fighter_name,peak_rating.

import argparse
from pathlib import Path
import pandas as pd
import re

SPACE_RE = re.compile(r"\s+")

def norm(s: str) -> str:
    if pd.isna(s):
        return ""
    return SPACE_RE.sub(" ", str(s).strip())

def build_long_from_history(hist: pd.DataFrame) -> pd.DataFrame:
    """One row per fighter per fight with post-fight rating + metadata."""
    hist = hist.copy()
    hist["DATE"] = pd.to_datetime(hist["DATE"], errors="coerce")

    a = hist[["DATE","EVENT","BOUT","fighter_a_id","fighter_a_name","pre_rating_a","post_rating_a"]].copy()
    a.columns = ["DATE","EVENT","BOUT","fighter_id","fighter_name","pre_rating","post_rating"]

    b = hist[["DATE","EVENT","BOUT","fighter_b_id","fighter_b_name","pre_rating_b","post_rating_b"]].copy()
    b.columns = ["DATE","EVENT","BOUT","fighter_id","fighter_name","pre_rating","post_rating"]

    long_df = pd.concat([a, b], ignore_index=True)
    long_df["fighter_id"] = long_df["fighter_id"].map(norm)
    long_df["fighter_name"] = long_df["fighter_name"].map(norm)
    long_df.loc[long_df["fighter_name"].eq(""), "fighter_name"] = long_df.loc[
        long_df["fighter_name"].eq(""), "fighter_id"
    ]
    long_df["post_rating"] = pd.to_numeric(long_df["post_rating"], errors="coerce")
    return long_df

def compute_peak(long_df: pd.DataFrame) -> pd.DataFrame:
    """For each fighter, pick earliest date of the max post_rating."""
    sort_df = long_df.sort_values(
        by=["fighter_id", "post_rating", "DATE"],
        ascending=[True, False, True],
        kind="stable",
    )
    peak = sort_df.drop_duplicates(subset=["fighter_id"], keep="first").rename(
        columns={
            "DATE": "peak_date",
            "EVENT": "peak_event",
            "BOUT": "peak_bout",
            "post_rating": "peak_rating",
        }
    )
    peak = peak[["fighter_id","fighter_name","peak_rating","peak_date","peak_event","peak_bout"]]
    peak = peak.sort_values("peak_rating", ascending=False).reset_index(drop=True)
    return peak

def main():
    ap = argparse.ArgumentParser(description="Compute peak Elo per fighter from elo_history.csv")
    ap.add_argument("-i", "--input", type=Path, required=True, help="Path to build/elo_history.csv")
    ap.add_argument("-o", "--output", type=Path, default=Path("build/elo_peak_ratings.csv"),
                    help="Output CSV (detailed)")
    ap.add_argument("--out-simple", type=Path, default=Path("build/elo_peak_ratings_simple.csv"),
                    help="Output CSV (fighter_name,peak_rating)")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    needed = {"fighter_a_id","fighter_b_id","fighter_a_name","fighter_b_name",
              "post_rating_a","post_rating_b","DATE","EVENT","BOUT"}
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise SystemExit(f"[ERROR] {args.input} missing required columns: {missing}")

    long_df = build_long_from_history(df)
    peak_df = compute_peak(long_df)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    peak_df.to_csv(args.output, index=False)

    # Simple two-column export
    simple = peak_df[["fighter_name", "peak_rating"]].copy()
    simple.to_csv(args.out_simple, index=False)

    print(f"[OK] Wrote {len(peak_df)} fighters to {args.output} "
          f"and {args.out_simple}")

if __name__ == "__main__":
    main()