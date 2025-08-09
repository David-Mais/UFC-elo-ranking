# load_and_prepare.py
# Step 1: Build a unified fights table (UFC-only) from your CSVs.

import argparse
import re
import sys
from pathlib import Path
import pandas as pd

# --------- Helpers ---------
SPACE_RE = re.compile(r"\s+")

def normalize_name(s: str) -> str:
    if pd.isna(s):
        return ""
    # strip, collapse spaces, remove stray commas/double spaces, keep case for display but return both
    s = s.strip()
    s = SPACE_RE.sub(" ", s)
    return s

def normalize_key(s: str) -> str:
    # A lowercase comparison key for joins (no accents handling to avoid extra deps)
    return normalize_name(s).lower()

def split_bout(bout: str):
    """
    Split 'Name A vs. Name B' into (A, B).
    Handles extra spaces like 'A  vs.  B'.
    """
    if pd.isna(bout):
        return "", ""
    bout_norm = SPACE_RE.sub(" ", bout.strip())
    # common separators: ' vs. ', 'vs.', 'vs ', ' v '
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", bout_norm, flags=re.IGNORECASE)
    if len(parts) != 2:
        # If split fails, try a last-ditch split on comma or hyphen (rare)
        return bout_norm, ""
    return normalize_name(parts[0]), normalize_name(parts[1])

def parse_outcome_label(outcome: str) -> str:
    """
    Map UFC Stats OUTCOME strings to labels:
    - 'W/L' -> A wins
    - 'L/W' -> B wins
    - contains 'D/D' -> draw
    - contains 'NC' or 'N/C' -> no contest (nc)
    """
    if pd.isna(outcome):
        return "unknown"
    o = outcome.strip().upper().replace(" ", "")
    if "W/L" in o:
        return "A"
    if "L/W" in o:
        return "B"
    if "D/D" in o or "DRAW" in o:
        return "draw"
    if "NC" in o or "N/C" in o:
        return "nc"
    return "unknown"

def parse_rounds_scheduled(time_format: str) -> int:
    """
    Parse '5 Rnd (5-5-5-5-5)' -> 5, '3 Rnd (...)' -> 3.
    If missing, default to 3.
    """
    if pd.isna(time_format):
        return 3
    m = re.search(r"(\d+)\s*Rnd", time_format)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 3

def decision_type_from_method(method: str) -> str:
    """
    Quick categorization for decisions from METHOD string (fallback; we’ll refine in Step 2).
    """
    if pd.isna(method):
        return "other"
    m = method.lower()
    if "decision" not in m:
        return "other"
    if "unanimous" in m:
        return "unanimous"
    if "split" in m:
        return "split"
    if "majority" in m:
        return "majority"
    return "decision"

# --------- Main pipeline ---------

def build_unified_fights(
    events_csv: Path,
    results_csv: Path,
    fighters_tot_csv: Path | None,
) -> pd.DataFrame:
    # Load events (DATE is needed for chronological order)
    events = pd.read_csv(events_csv)
    for col in ("EVENT", "DATE"):
        if col not in events.columns:
            raise ValueError(f"{events_csv} missing required column: {col}")
    events["EVENT_KEY"] = events["EVENT"].map(normalize_key)
    events["DATE"] = pd.to_datetime(events["DATE"], errors="coerce")

    # Load results (main driver)
    results = pd.read_csv(results_csv)
    needed = ("EVENT", "BOUT", "OUTCOME", "WEIGHTCLASS", "METHOD", "ROUND", "TIME FORMAT", "REFEREE", "DETAILS", "URL")
    for col in needed:
        if col not in results.columns:
            raise ValueError(f"{results_csv} missing required column: {col}")
    results["EVENT_KEY"] = results["EVENT"].map(normalize_key)

    # Join DATE from events
    fights = results.merge(
        events[["EVENT_KEY", "DATE"]],
        on="EVENT_KEY",
        how="left",
        validate="many_to_one",
    )

    # Parse fighters (A on the left; B on the right)
    a_names = []
    b_names = []
    for bout in fights["BOUT"].astype(str):
        a, b = split_bout(bout)
        a_names.append(a)
        b_names.append(b)
    fights["fighter_a_name"] = a_names
    fights["fighter_b_name"] = b_names

    # Outcome label
    fights["winner_label"] = fights["OUTCOME"].map(parse_outcome_label)

    # Rounds scheduled (3 vs 5)
    fights["rounds_scheduled"] = fights["TIME FORMAT"].map(parse_rounds_scheduled)

    # Simple decision type (unanimous/split/majority/other) - Step 2 will refine dominance
    fights["decision_type"] = fights["METHOD"].map(decision_type_from_method)

    # Optional: map fighter names to fighter URLs (stable IDs) from UFC_fighter_tott.csv
    if fighters_tot_csv is not None:
        tot = pd.read_csv(fighters_tot_csv)
        if not {"FIGHTER", "URL"}.issubset(tot.columns):
            raise ValueError(f"{fighters_tot_csv} must include FIGHTER and URL")
        tot["FIGHTER_KEY"] = tot["FIGHTER"].map(normalize_key)

        fights["fighter_a_key"] = fights["fighter_a_name"].map(normalize_key)
        fights["fighter_b_key"] = fights["fighter_b_name"].map(normalize_key)

        # Left merge for A and B separately
        fights = fights.merge(
            tot[["FIGHTER_KEY", "URL"]].rename(columns={"FIGHTER_KEY": "fighter_a_key", "URL": "fighter_a_url"}),
            on="fighter_a_key",
            how="left",
        ).merge(
            tot[["FIGHTER_KEY", "URL"]].rename(columns={"FIGHTER_KEY": "fighter_b_key", "URL": "fighter_b_url"}),
            on="fighter_b_key",
            how="left",
        )

    # Select & order columns for the unified CSV
    cols = [
        "DATE",
        "EVENT",
        "BOUT",
        "fighter_a_name",
        "fighter_b_name",
        "winner_label",
        "WEIGHTCLASS",
        "METHOD",
        "decision_type",
        "ROUND",
        "TIME",
        "TIME FORMAT",
        "REFEREE",
        "DETAILS",
        "URL",
        "rounds_scheduled",
    ]
    if "fighter_a_url" in fights.columns:
        cols += ["fighter_a_url", "fighter_b_url"]

    fights_unified = fights[cols].sort_values(["DATE", "EVENT", "BOUT"], kind="stable").reset_index(drop=True)
    return fights_unified

def main():
    parser = argparse.ArgumentParser(description="Step 1: Build a unified fights table from UFC CSVs.")
    parser.add_argument("--events", required=True, type=Path, help="Path to ufc_event_details.csv")
    parser.add_argument("--results", required=True, type=Path, help="Path to ufc_fight_results.csv")
    parser.add_argument("--fighters", required=False, type=Path, help="Path to UFC_fighter_tott.csv (optional)")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Output CSV path (e.g., build/fights_unified.csv)")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        df = build_unified_fights(args.events, args.results, args.fighters)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    df.to_csv(args.output, index=False)
    print(f"[OK] Wrote {len(df)} rows to {args.output}")

if __name__ == "__main__":
    main()
