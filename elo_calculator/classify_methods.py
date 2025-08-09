import argparse
import re
import sys
from pathlib import Path
import pandas as pd

SPACE_RE = re.compile(r"\s+")
SCORE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")  # e.g., "48 - 47" or "48–47"

FINISH_TOKENS = (
    "ko", "tko", "submission", "sub", "dq", "disqualification",
    "doctor stoppage", "retirement"
)

def normalize_text(s: str) -> str:
    if pd.isna(s):
        return ""
    s = s.strip()
    s = SPACE_RE.sub(" ", s)
    return s

def scheduled_rounds_from_timefmt(timefmt: str) -> int:
    if pd.isna(timefmt):
        return 3
    m = re.search(r"(\d+)\s*Rnd", str(timefmt))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 3

def parse_scorecard_margins(details_text: str) -> list[int]:
    """
    Extract judge totals from DETAILS and return absolute margins per card.
    Example DETAILS:
      "Ben Cartlidge 47 - 48.Mike Bell 48 - 47.David Lethaby 47 - 48."
    -> margins [1, 1, 1]
    """
    if pd.isna(details_text) or not str(details_text).strip():
        return []
    text = details_text.replace(",", " ")
    # Some rows have multiple sentences; just find all number pairs A-B
    margins = []
    for a, b in SCORE_RE.findall(text):
        try:
            margins.append(abs(int(a) - int(b)))
        except Exception:
            continue
    return margins

def method_is_finish(method: str) -> bool:
    m = normalize_text(method).lower()
    return any(tok in m for tok in FINISH_TOKENS)

def method_is_decision(method: str) -> bool:
    return "decision" in normalize_text(method).lower()

def method_decision_type(method: str) -> str:
    m = normalize_text(method).lower()
    if "split" in m:
        return "split"
    if "majority" in m:
        return "majority"
    if "unanimous" in m:
        return "unanimous"
    return "decision"

def classify_row(row, m_finish: float, m_dom: float, m_dec: float):
    """
    Returns a tuple:
      (method_class, method_multiplier, decision_basis, judge_margins_str)
    method_class in {"finish","decision_dominant","decision_normal","draw","nc","other"}
    """
    outcome = normalize_text(row.get("winner_label", ""))
    method = normalize_text(row.get("METHOD", ""))
    details = normalize_text(row.get("DETAILS", ""))
    timefmt = normalize_text(row.get("TIME FORMAT", ""))
    rounds_scheduled = row.get("rounds_scheduled", None)
    if pd.isna(rounds_scheduled):
        rounds_scheduled = scheduled_rounds_from_timefmt(timefmt)

    # Handle draws/NCs up front
    if outcome.lower() == "draw":
        return ("draw", m_dec, "outcome_draw", "")
    if outcome.lower() == "nc":
        return ("nc", m_dec, "outcome_nc", "")

    # Finishes
    if method_is_finish(method) and not method_is_decision(method):
        return ("finish", m_finish, "method_finish", "")

    # Decisions
    if method_is_decision(method):
        d_type = method_decision_type(method)
        # Split / majority are always "normal" by our policy
        if d_type in ("split", "majority"):
            return ("decision_normal", m_dec, f"method_{d_type}", "")

        # Unanimous / generic decision: try to use DETAILS margins if present
        margins = parse_scorecard_margins(details)
        margins_str = ",".join(str(x) for x in margins) if margins else ""

        # Dominance heuristics (apply the same for 3r/5r):
        # - any card margin >= 3 -> dominant
        # - OR at least two cards with margin >= 2 -> dominant
        if margins:
            if any(m >= 3 for m in margins):
                return ("decision_dominant", m_dom, "details_any_margin_ge_3", margins_str)
            if sum(1 for m in margins if m >= 2) >= 2:
                return ("decision_dominant", m_dom, "details_two_cards_ge_2", margins_str)
            # Otherwise normal, even if unanimous but all 48-47 type cards
            return ("decision_normal", m_dec, "details_small_margins", margins_str)

        # No DETAILS → use METHOD keyword
        if d_type == "unanimous":
            return ("decision_dominant", m_dom, "method_unanimous_no_details", "")
        return ("decision_normal", m_dec, "method_generic_decision", "")

    # Fallback: treat other stoppages as finishes if they slipped through (rare),
    # otherwise mark as 'other' with neutral multiplier.
    if any(tok in method.lower() for tok in FINISH_TOKENS):
        return ("finish", m_finish, "method_finish_fallback", "")
    return ("other", m_dec, "unknown_method", "")

def main():
    parser = argparse.ArgumentParser(description="Step 2: Classify bouts and attach method multipliers.")
    parser.add_argument("-i", "--input", required=True, type=Path, help="Input CSV from Step 1 (build/fights_unified.csv)")
    parser.add_argument("-o", "--output", required=True, type=Path, help="Output CSV path (e.g., build/fights_classified.csv)")
    parser.add_argument("--m-finish", type=float, default=1.20, help="Multiplier for finishes (default 1.20)")
    parser.add_argument("--m-dom", type=float, default=1.10, help="Multiplier for dominant decisions (default 1.10)")
    parser.add_argument("--m-dec", type=float, default=1.00, help="Multiplier for normal decisions/draws/NC (default 1.00)")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_csv(args.input)
    except Exception as e:
        print(f"[ERROR] Failed to read {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    required = [
        "DATE", "EVENT", "BOUT",
        "fighter_a_name", "fighter_b_name",
        "winner_label", "METHOD", "DETAILS", "TIME FORMAT"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing required columns in input: {missing}", file=sys.stderr)
        sys.exit(1)

    # Ensure rounds_scheduled exists (Step 1 should have it)
    if "rounds_scheduled" not in df.columns:
        df["rounds_scheduled"] = df["TIME FORMAT"].map(scheduled_rounds_from_timefmt)

    # Classify each row
    method_class = []
    method_mult = []
    decision_basis = []
    judge_margins = []

    for _, row in df.iterrows():
        cls, mult, basis, margins_str = classify_row(row, args.__dict__["m_finish"], args.__dict__["m_dom"], args.__dict__["m_dec"])
        method_class.append(cls)
        method_mult.append(mult)
        decision_basis.append(basis)
        judge_margins.append(margins_str)

    df["method_class"] = method_class
    df["method_multiplier"] = method_mult
    df["decision_basis"] = decision_basis
    df["judge_margins"] = judge_margins

    # Order columns nicely
    col_order = [
        "DATE", "EVENT", "BOUT",
        "fighter_a_name", "fighter_b_name",
        "winner_label",
        "WEIGHTCLASS", "METHOD", "decision_type",  # decision_type came from Step 1; keep it if present
        "method_class", "method_multiplier", "decision_basis", "judge_margins",
        "ROUND", "TIME", "TIME FORMAT", "rounds_scheduled",
        "REFEREE", "DETAILS", "URL"
    ]
    # Keep any ID columns if they exist
    for extra in ("fighter_a_url", "fighter_b_url"):
        if extra in df.columns and extra not in col_order:
            col_order.append(extra)

    # Some columns might be missing (e.g., decision_type). Keep only those that exist.
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order].sort_values(["DATE", "EVENT", "BOUT"], kind="stable").reset_index(drop=True)

    try:
        df.to_csv(args.output, index=False)
    except Exception as e:
        print(f"[ERROR] Failed to write {args.output}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Wrote {len(df)} rows to {args.output}")

if __name__ == "__main__":
    main()
