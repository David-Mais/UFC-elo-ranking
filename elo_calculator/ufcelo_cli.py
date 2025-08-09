import argparse, os, sys, subprocess, shlex
from pathlib import Path

HERE = Path(__file__).resolve().parent

def find_script(name: str) -> Path:
    # Try current working directory first, then alongside this CLI
    cwd = Path.cwd()
    cand = [cwd / name, HERE / name]

    for p in cand:
        if p.exists():
            return p
    raise FileNotFoundError(f"Could not find {name}. Looked in: " + ", ".join(str(p) for p in cand))

def ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def run_cmd(args_list: list, check=True) -> int:
    cmd_str = " ".join(shlex.quote(str(a)) for a in args_list)
    print(f"\n↪ Running: {cmd_str}")
    proc = subprocess.run(args_list)
    if check and proc.returncode != 0:
        sys.exit(proc.returncode)
    return proc.returncode

def load_config(path: Path | None) -> dict:
    if not path:
        return {}
    if not path.exists():
        print(f"[warn] config file not found: {path}")
        return {}
    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except Exception:
                print("[warn] PyYAML not installed; install with `pip install pyyaml` to use YAML configs.")
                return {}
            return dict(yaml.safe_load(path.read_text()) or {})
        elif path.suffix.lower() == ".json":
            import json
            return json.loads(path.read_text())
        else:
            print(f"[warn] unknown config extension {path.suffix}; expected .yaml/.yml/.json")
            return {}
    except Exception as e:
        print(f"[warn] failed to parse config: {e}")
        return {}

# --------------- Commands ---------------

def cmd_prepare(args):
    script = find_script("load_and_prepare.py")
    out = Path(args.out or "../build/fights_unified.csv")
    ensure_dir(out)
    base = [sys.executable, str(script), "--events", args.events, "--results", args.results, "-o", str(out)]
    if args.fighters:
        base += ["--fighters", args.fighters]
    return run_cmd(base)

def cmd_classify(args):
    script = find_script("classify_methods.py")
    out = Path(args.out or "../build/fights_classified.csv")
    ensure_dir(out)
    cmd = [sys.executable, str(script), "-i", args.input, "-o", str(out)]
    if args.m_finish is not None: cmd += ["--m-finish", str(args.m_finish)]
    if args.m_dom is not None: cmd += ["--m-dom", str(args.m_dom)]
    if args.m_dec is not None: cmd += ["--m-dec", str(args.m_dec)]
    return run_cmd(cmd)

def cmd_elo(args):
    script = find_script("elo_update.py")
    out_hist = Path(args.out_history or "../build/elo_history.csv")
    out_ratings = Path(args.out_ratings or "../build/elo_ratings_current.csv")
    out_simple = Path(args.out_ratings_simple or "../build/elo_ratings_simple.csv")
    for p in (out_hist, out_ratings, out_simple):
        ensure_dir(p)
    cmd = [
        sys.executable, str(script),
        "-i", args.input,
        "--out-history", str(out_hist),
        "--out-ratings", str(out_ratings),
        "--out-ratings-simple", str(out_simple),
    ]
    if args.K is not None: cmd += ["--K", str(args.K)]
    if args.scale is not None: cmd += ["--scale", str(args.scale)]
    if args.base_rating is not None: cmd += ["--base-rating", str(args.base_rating)]
    return run_cmd(cmd)

def cmd_peak(args):
    script = find_script("compute_peak_elo.py")
    out = Path(args.out or "../build/elo_peak_ratings.csv")
    out_simple = Path(args.out_simple or "../build/elo_peak_ratings_simple.csv")
    ensure_dir(out)
    ensure_dir(out_simple)
    cmd = [sys.executable, str(script), "-i", args.input, "-o", str(out), "--out-simple", str(out_simple)]
    return run_cmd(cmd)

def cmd_run_all(args):
    cfg = load_config(Path(args.config) if args.config else None)

    # Resolve paths (config -> args -> defaults)
    data_cfg = cfg.get("data", {})
    build_cfg = cfg.get("build", {})
    params_cfg = cfg.get("params", {})

    events = args.events or data_cfg.get("events")
    results = args.results or data_cfg.get("results")
    fighters = args.fighters or data_cfg.get("fighters")
    if not events or not results:
        print("ERROR: events and results are required. Provide via flags or config."); sys.exit(2)

    build_dir = Path(build_cfg.get("dir", "../build"))
    unified = str(build_dir / build_cfg.get("unified", "fights_unified.csv"))
    classified = str(build_dir / build_cfg.get("classified", "fights_classified.csv"))
    elo_history = str(build_dir / build_cfg.get("elo_history", "elo_history.csv"))
    elo_ratings = str(build_dir / build_cfg.get("elo_ratings", "elo_ratings_current.csv"))
    elo_ratings_simple = str(build_dir / build_cfg.get("elo_ratings_simple", "elo_ratings_simple.csv"))
    peak = str(build_dir / build_cfg.get("peak", "elo_peak_ratings.csv"))
    peak_simple = str(build_dir / build_cfg.get("peak_simple", "elo_peak_ratings_simple.csv"))

    # Prepare
    print("\n== Step 1/4: Prepare (unify fights) ==")
    cmd_prepare(argparse.Namespace(events=events, results=results, fighters=fighters, out=unified))

    # Classify
    print("\n== Step 2/4: Classify methods ==")
    mcfg = (params_cfg.get("classify") or {})
    cmd_classify(argparse.Namespace(
        input=unified, out=classified,
        m_finish=args.m_finish if args.m_finish is not None else mcfg.get("m_finish"),
        m_dom=args.m_dom if args.m_dom is not None else mcfg.get("m_dom"),
        m_dec=args.m_dec if args.m_dec is not None else mcfg.get("m_dec"),
    ))

    # Elo
    print("\n== Step 3/4: Elo update ==")
    ecfg = (params_cfg.get("elo") or {})
    cmd_elo(argparse.Namespace(
        input=classified,
        out_history=elo_history,
        out_ratings=elo_ratings,
        out_ratings_simple=elo_ratings_simple,
        K=args.K if args.K is not None else ecfg.get("K"),
        scale=args.scale if args.scale is not None else ecfg.get("scale"),
        base_rating=args.base_rating if args.base_rating is not None else ecfg.get("base_rating"),
    ))

    # Peak Elo
    print("\n== Step 4/4: Peak Elo ==")
    cmd_peak(argparse.Namespace(input=elo_history, out=peak, out_simple=peak_simple))

# --------------- Parser ---------------

def build_parser():
    p = argparse.ArgumentParser(prog="ufcelo", description="UFC Elo pipeline wrapper")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("prepare", help="Unify fights (clean + join + sort)")
    sp.add_argument("--events", required=True)
    sp.add_argument("--results", required=True)
    sp.add_argument("--fighters", required=False, help="Optional fighter URL map CSV")
    sp.add_argument("-o", "--out", required=False, help="Output unified CSV (default: build/fights_unified.csv)")
    sp.set_defaults(func=cmd_prepare)

    sc = sub.add_parser("classify", help="Classify method (finish/dom/decision)")
    sc.add_argument("-i", "--input", required=True)
    sc.add_argument("-o", "--out", required=False, help="Output classified CSV (default: build/fights_classified.csv)")
    sc.add_argument("--m-finish", type=float, dest="m_finish")
    sc.add_argument("--m-dom", type=float, dest="m_dom")
    sc.add_argument("--m-dec", type=float, dest="m_dec")
    sc.set_defaults(func=cmd_classify)

    se = sub.add_parser("elo", help="Run Elo updates")
    se.add_argument("-i", "--input", required=True)
    se.add_argument("--out-history", required=False, help="Output Elo history CSV (default: build/elo_history.csv)")
    se.add_argument("--out-ratings", required=False, help="Output latest ratings CSV (default: build/elo_ratings_current.csv)")
    se.add_argument("--out-ratings-simple", required=False, help="Output simple ratings CSV (default: build/elo_ratings_simple.csv)")
    se.add_argument("--K", type=float)
    se.add_argument("--scale", type=float)
    se.add_argument("--base-rating", type=float, dest="base_rating")
    se.set_defaults(func=cmd_elo)

    spk = sub.add_parser("peak", help="Compute peak Elo from history")
    spk.add_argument("-i", "--input", required=True)
    spk.add_argument("-o", "--out", required=False, help="Output peak Elo CSV (default: build/elo_peak_ratings.csv)")
    spk.add_argument("--out-simple", required=False, dest="out_simple", help="Output simple peak CSV (default: build/elo_peak_ratings_simple.csv)")
    spk.set_defaults(func=cmd_peak)

    ra = sub.add_parser("run-all", help="Run the whole pipeline (prepare -> classify -> elo -> peak)")
    ra.add_argument("--events")
    ra.add_argument("--results")
    ra.add_argument("--fighters")
    ra.add_argument("--config", help="Optional YAML/JSON config to fill defaults")
    # Optional overrides
    ra.add_argument("--m-finish", type=float, dest="m_finish")
    ra.add_argument("--m-dom", type=float, dest="m_dom")
    ra.add_argument("--m-dec", type=float, dest="m_dec")
    ra.add_argument("--K", type=float)
    ra.add_argument("--scale", type=float)
    ra.add_argument("--base-rating", type=float, dest="base_rating")
    ra.set_defaults(func=cmd_run_all)

    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())