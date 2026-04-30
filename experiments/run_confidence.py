"""
Modul C — calibration + formal pre-reg batch.

Két fázis:

1. CALIBRATION (5 seed × 3000 step, NEM pre-reg):
   - Baseline daemon + confidence_computer + meta-monitor (log_only)
   - Minden hozzáadott élre confidence_score komponensei kiszámolva
   - Q1, Q2, Q3 és surprise_median rögzítve

2. FORMAL (30 seed × 3000 step, pre-reg):
   - Ugyanaz, mint calibration, csak több seed
   - A calibrált küszöbökkel címkézünk
   - C-H1: near_contradiction vs proven contradiction-rate
   - C-H2: Spearman ρ confidence_score vs waking_pass
   - Incremental R²: confidence_score additív magyarázó ereje
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import median, mean

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_policy(seed: int, log_dir: Path) -> Path:
    data = {
        "discovery": {
            "enabled": True, "daemon_mode": True, "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False, "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "telemetry_log_path": str(log_dir / f"seed_{seed:03d}.tel"),
            "log_path": str(log_dir / f"seed_{seed:03d}.disc"),
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
            "hypnagogic": {"enabled": False},
        }
    }
    tf = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


def collect_edge_records(
    seed: int, n_steps: int, registry: Path, log_dir: Path,
    chain_depth_cap: int = 5,
) -> list:
    """Egy seed: futtatja az engine-t, minden hozzáadott élre kiszámolja a
    4 input-jelt + nyers értékeket. Visszaadja a rekordokat."""
    from axiom_kernel import AxiomaticInferenceEngine
    from confidence_score import ConfidenceComputer
    from meta_monitor import StuckDetector

    policy = _build_policy(seed, log_dir)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy), registry_path=str(registry),
        )
        # Modul D detector log_only módban — ad stuck eseményeket a confidence-be
        det = StuckDetector(window_size=500, repetition_threshold=3, granularity="pair")
        eng.attach_meta_monitor(det, intervention_mode="log_only")
        # Modul C: confidence_computer
        cc = ConfidenceComputer(chain_depth_cap=chain_depth_cap)
        eng.attach_confidence_computer(cc)

        # Snapshot of initial matrix
        A0 = eng.knowledge_matrix.copy()

        # Minden hozzáadott él rekordját a felvétel pillanatában gyűjtjük.
        edge_records = []
        prev_matrix = A0.copy()
        for step in range(n_steps):
            eng.think_step()
            snap = eng._last_think_snapshot
            # Új él esetén compute
            if snap.edge_added and snap.i is not None and snap.j is not None:
                A_now = eng.knowledge_matrix
                # A compute az AKTUÁLIS állapoton fut, ami már tartalmazza ezt az élt;
                # a chain_depth és contradiction_distance az aktuális gráfon
                result = cc.compute(
                    A_now, snap.i, snap.j,
                    negation_map=eng._negation,
                    current_step=step,
                    axiom_labels=eng.axiom_labels,
                )
                # Statikus mező: is_in_contradiction (a felvétel utáni állapotban)
                # Ezt a contradiction_distance < ∞ jelzi
                cd = result["raw"]["contradiction_distance"]
                is_in_contradiction = (cd != float("inf")) and (cd <= 5.0)
                # Statikus mező: waking_pass_strict
                # NEM forbidden ÉS NEM contradiction-rejected
                fbe = eng._registry.forbidden_edges if eng._registry else set()
                is_forbidden = (snap.i, snap.j) in fbe
                # Recompute contradiction without the (i,j) edge to test pass
                neg_j = eng._negation.get(snap.j)
                contradicts = False
                if neg_j is not None:
                    old = A_now[snap.i, snap.j]
                    A_now[snap.i, snap.j] = 0.0
                    contradicts = eng._has_path_unlocked(A_now, snap.i, neg_j)
                    A_now[snap.i, snap.j] = old
                waking_pass_strict = not (is_forbidden or contradicts)

                edge_records.append({
                    "seed": seed, "step": step,
                    "i": int(snap.i), "j": int(snap.j),
                    "confidence_score": result["confidence_score"],
                    "min_component": result["min_component"],
                    "chain_depth_score": result["components"]["chain_depth"],
                    "surprise_inverse_score": result["components"]["surprise_inverse"],
                    "stuck_history_score": result["components"]["stuck_history"],
                    "contradiction_distance_score": result["components"]["contradiction_distance"],
                    "chain_depth_n_paths": result["raw"]["chain_depth_n_paths"],
                    "surprise_raw": result["raw"]["surprise_raw"],
                    "stuck_raw": result["raw"]["stuck_raw"],
                    "contradiction_distance_raw": (
                        result["raw"]["contradiction_distance"]
                        if not math.isinf(result["raw"]["contradiction_distance"])
                        else -1.0
                    ),
                    "is_in_contradiction": bool(is_in_contradiction),
                    "waking_pass_strict": bool(waking_pass_strict),
                })
        return edge_records
    finally:
        policy.unlink(missing_ok=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["calibrate", "formal"], default="formal")
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--chain-depth-cap", type=int, default=5)
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    ap.add_argument("--registry", type=Path,
                    default=ROOT / "experiments" / "registries" / "E_daemon_baseline.json")
    args = ap.parse_args()

    out_dir = args.out_root / f"C_{args.mode}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Modul C {args.mode} ({args.n_seeds} seed × {args.n_steps} step) ===")
    print(f"  registry: {args.registry}")
    print(f"  chain_depth_cap: {args.chain_depth_cap}")

    t0 = time.time()
    all_records = []
    if args.workers <= 1:
        for s in range(args.n_seeds):
            recs = collect_edge_records(s, args.n_steps, args.registry, out_dir, args.chain_depth_cap)
            all_records.extend(recs)
            print(f"  [seed={s}] {len(recs)} edges", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(collect_edge_records, s, args.n_steps, args.registry, out_dir, args.chain_depth_cap): s
                    for s in range(args.n_seeds)}
            for fut in as_completed(futs):
                recs = fut.result()
                all_records.extend(recs)
                seed = recs[0]["seed"] if recs else "?"
                print(f"  [seed={seed}] {len(recs)} edges", flush=True)

    print(f"\nÖssz idő: {time.time()-t0:.0f} s, {len(all_records)} él gyűjtve")

    out_path = out_dir / "edge_records.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=1)
    print(f"Mentés: {out_path}")

    # Calibration módban: kvantilisek számítása
    if args.mode == "calibrate":
        confidences = sorted([r["confidence_score"] for r in all_records])
        surprises = sorted([r["surprise_raw"] for r in all_records])
        chain_depth_n = sorted([r["chain_depth_n_paths"] for r in all_records])

        def q(arr, p):
            if not arr:
                return float("nan")
            idx = int(p * (len(arr) - 1))
            return arr[idx]

        cal = {
            "n_records": len(all_records),
            "confidence_q1": q(confidences, 0.25),
            "confidence_q2": q(confidences, 0.50),
            "confidence_q3": q(confidences, 0.75),
            "surprise_median": q(surprises, 0.50),
            "chain_depth_p95": q(chain_depth_n, 0.95),
        }
        cal_path = out_dir / "calibration.json"
        with cal_path.open("w", encoding="utf-8") as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
        print()
        print("CALIBRATION OUTPUT:")
        print(f"  Q1 = {cal['confidence_q1']:.4f}")
        print(f"  Q2 = {cal['confidence_q2']:.4f}")
        print(f"  Q3 = {cal['confidence_q3']:.4f}")
        print(f"  surprise_median = {cal['surprise_median']:.4f}")
        print(f"  chain_depth_p95 = {cal['chain_depth_p95']}")
        print(f"  -> N_CAP javaslat = {max(5, int(cal['chain_depth_p95']))}")


if __name__ == "__main__":
    main()
