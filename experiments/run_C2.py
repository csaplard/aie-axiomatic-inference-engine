"""
Modul C v2 — attempted-edge tracker + 3-osztályú klasszifikációs runner.

Két fázis a `--mode` flag alapján:
  - confound: 3 seed, 2000 step → outcome-osztály eloszlás (healthy zone check)
  - formal:   30 seed, 3000 step → C2-H1 + C2-H2 elemzés

Bemenő regiszter: experiments/registries/C2_domain_negation.json
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

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


def collect_attempts(seed: int, n_steps: int, registry: Path, log_dir: Path) -> list:
    """1 seed × n_steps: minden attempted élre rögzít egy rekordot
    (confidence + 4 input + outcome)."""
    from axiom_kernel import AxiomaticInferenceEngine
    from confidence_score import ConfidenceComputer
    from meta_monitor import StuckDetector
    from attempted_edge_logger import AttemptedEdgeLogger

    policy = _build_policy(seed, log_dir)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy), registry_path=str(registry),
        )
        # Detector log_only — stuck-history forrás
        det = StuckDetector(window_size=500, repetition_threshold=3, granularity="pair")
        eng.attach_meta_monitor(det, intervention_mode="log_only")
        # Confidence computer
        cc = ConfidenceComputer(chain_depth_cap=5)
        eng.attach_confidence_computer(cc)
        logger = AttemptedEdgeLogger()

        for step in range(n_steps):
            # PRE-attempt mátrix snapshot a confidence_score számoláshoz
            A_pre = eng.knowledge_matrix.copy()
            eng.think_step()
            snap = eng._last_think_snapshot
            outcome = AttemptedEdgeLogger.classify_outcome(snap)

            # Egyetlen érdekes alosztály: az "exists" és "no_pair" triviálisak
            if outcome in ("no_pair", "exists"):
                continue

            # confidence_score a PRE-attempt mátrixon (pre-reg tisztaság)
            if snap.i is None or snap.j is None:
                continue
            result = cc.compute(
                A_pre, snap.i, snap.j,
                negation_map=eng._negation,
                current_step=step,
                axiom_labels=eng.axiom_labels,
            )
            cdr = result["raw"]["contradiction_distance"]
            cdr_serialized = -1.0 if math.isinf(cdr) else float(cdr)

            logger.record({
                "seed": seed, "step": step,
                "i": int(snap.i), "j": int(snap.j),
                "outcome": outcome,
                "confidence_score": float(result["confidence_score"]),
                "min_component": result["min_component"],
                "chain_depth_score": result["components"]["chain_depth"],
                "surprise_inverse_score": result["components"]["surprise_inverse"],
                "stuck_history_score": result["components"]["stuck_history"],
                "contradiction_distance_score": result["components"]["contradiction_distance"],
                "chain_depth_n_paths": result["raw"]["chain_depth_n_paths"],
                "surprise_raw": result["raw"]["surprise_raw"],
                "stuck_raw": result["raw"]["stuck_raw"],
                "contradiction_distance_raw": cdr_serialized,
            })
        return logger.all_records()
    finally:
        policy.unlink(missing_ok=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["confound", "formal"], default="formal")
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--registry", type=Path,
        default=ROOT / "experiments" / "registries" / "C2_domain_negation.json",
    )
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    args = ap.parse_args()

    out_dir = args.out_root / f"C2_{args.mode}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Modul C2 {args.mode} ({args.n_seeds} seed × {args.n_steps} step) ===")
    print(f"  registry: {args.registry}")

    t0 = time.time()
    all_records = []
    if args.workers <= 1:
        for s in range(args.n_seeds):
            recs = collect_attempts(s, args.n_steps, args.registry, out_dir)
            all_records.extend(recs)
            c = Counter(r["outcome"] for r in recs)
            print(f"  [seed={s}] {len(recs)} attempts | {dict(c)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(collect_attempts, s, args.n_steps, args.registry, out_dir): s
                    for s in range(args.n_seeds)}
            for fut in as_completed(futs):
                recs = fut.result()
                all_records.extend(recs)
                seed = recs[0]["seed"] if recs else "?"
                c = Counter(r["outcome"] for r in recs)
                print(f"  [seed={seed}] {len(recs)} attempts | {dict(c)}", flush=True)

    print(f"\n{len(all_records)} attempt összesen, {time.time()-t0:.0f} s")

    out_path = out_dir / "attempts.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=1)
    print(f"Mentés: {out_path}")

    # Outcome eloszlás
    print()
    print("Outcome eloszlás (összesen):")
    c = Counter(r["outcome"] for r in all_records)
    total = len(all_records)
    for k, v in c.most_common():
        print(f"  {k:20s}: {v:>6d}  ({v/total:.3f})")

    if args.mode == "confound":
        # Healthy-zone check
        accepted = c.get("accepted", 0) / max(total, 1)
        forbidden = c.get("forbidden", 0) / max(total, 1)
        contradiction = c.get("contradiction", 0) / max(total, 1)
        print()
        healthy = (
            0.50 <= accepted <= 0.95
            and 0.02 <= contradiction <= 0.30
            and 0.01 <= forbidden <= 0.20
        )
        print(f"  Healthy-zone check: accepted∈[0.5,0.95]={accepted:.3f}, "
              f"contra∈[0.02,0.30]={contradiction:.3f}, forbidden∈[0.01,0.20]={forbidden:.3f}")
        print(f"  -> {'HEALTHY' if healthy else 'OUT OF ZONE'}")


if __name__ == "__main__":
    main()
