"""
Modul D — formal pre-reg batch.

3 kar × 30 seed × 3000 lépés × n=80 × strict immune.
Calibrált paraméterek: W=500, M=3, granularity=pair.
"""

from __future__ import annotations

import json
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

# Calibrált paraméterek (a calibration-scan alapján)
W_CAL = 500
M_CAL = 3
GRAN_CAL = "pair"


def _build_policy(arm: str, seed: int, log_dir: Path) -> Path:
    """Policy YAML — meta_intervention karon hypnagogic engedélyezve."""
    is_intervention = (arm == "meta_intervention")
    data = {
        "discovery": {
            "enabled": True, "daemon_mode": True, "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False, "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "telemetry_log_path": str(log_dir / f"seed_{seed:03d}.tel"),
            "log_path": str(log_dir / f"seed_{seed:03d}.disc"),
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
            "hypnagogic": {
                # csak a meta_intervention karon kell ténylegesen aktív
                "enabled": is_intervention,
                "entry_steps": 7, "deep_steps": 30, "exit_steps": 7,
                "cooldown_steps": 200,
                "forbidden_weight_deep": 0.3,
                "negation_threshold_deep": 0.5,
                "far_domain_pref_deep": 0.6,
                "verify_chain_depth_deep": 3,
                "fisher_trigger_factor": 999.0,  # NE tüzeljen a Fisher-trigger
                "fisher_min_history": 9999,      # tényleg ne tüzeljen
                "log_path": str(log_dir / f"seed_{seed:03d}.hyp.jsonl"),
            },
        }
    }
    tf = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


def run_seed(arm: str, seed: int, n_steps: int, log_dir: Path, registry: Path) -> dict:
    from axiom_kernel import AxiomaticInferenceEngine
    from meta_monitor import StuckDetector

    policy = _build_policy(arm, seed, log_dir)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy), registry_path=str(registry),
        )
        # Snapshot of initial matrix
        A0 = eng.knowledge_matrix.copy()

        # Detector csatlakoztatás (kivéve baseline)
        detector = None
        if arm in ("meta_log_only", "meta_intervention"):
            detector = StuckDetector(
                window_size=W_CAL, repetition_threshold=M_CAL, granularity=GRAN_CAL,
            )
            mode = "log_only" if arm == "meta_log_only" else "hypnagogic"
            eng.attach_meta_monitor(detector, intervention_mode=mode, cooldown_steps=100)

        # Lépésenkénti pár-tracking (külön a max_repetition_density-hez az utolsó W lépésen)
        from collections import deque
        recent_pairs = deque(maxlen=W_CAL)

        for _ in range(n_steps):
            eng.think_step()
            snap = eng._last_think_snapshot
            if snap.i is not None and snap.j is not None:
                recent_pairs.append((int(snap.i), int(snap.j)))

        # Metrikák
        # 1. final Q
        final_q = eng.calculate_q()
        # 2. n_edges_added
        A = eng.knowledge_matrix
        diff = (A > 0) & (A0 == 0)
        np.fill_diagonal(diff, False)
        n_edges = int(diff.sum())
        # 3. far_domain_ratio
        idx_pairs = list(zip(*np.where(diff)))
        far = 0
        total = 0
        for i, j in idx_pairs:
            di = eng.axiom_labels.get(int(i))
            dj = eng.axiom_labels.get(int(j))
            if di is not None and dj is not None:
                total += 1
                if di != dj:
                    far += 1
        far_domain_ratio = far / total if total else float("nan")
        # 4. max repetition density az utolsó W=500 lépésben
        cnt = Counter(recent_pairs)
        max_rep = max(cnt.values()) if cnt else 0
        # 5. detector és intervenció statisztikák
        det_attempts = detector.attempt_count if detector else 0
        det_fires = detector.fire_count if detector else 0
        det_fire_rate = detector.fire_rate() if detector else 0.0
        intervention_count = (
            eng._intervention_manager.intervention_count
            if eng._intervention_manager is not None else 0
        )
        return {
            "arm": arm, "seed": seed,
            "n_edges_added": n_edges,
            "final_q": final_q,
            "far_domain_ratio": far_domain_ratio,
            "max_repetition_last_W": max_rep,
            "detector_attempts": det_attempts,
            "detector_fires": det_fires,
            "detector_fire_rate": det_fire_rate,
            "intervention_count": intervention_count,
        }
    finally:
        policy.unlink(missing_ok=True)


def run_arm(arm: str, n_seeds: int, n_steps: int, out_root: Path, registry: Path, workers: int = 4) -> list:
    out_dir = out_root / f"D_{arm}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== arm: {arm} ({n_seeds} seed × {n_steps} steps, {workers} workers) ===")
    results = []
    if workers <= 1:
        for s in range(n_seeds):
            r = run_seed(arm, s, n_steps, out_dir, registry)
            results.append(r)
            print(f"  [seed={s}] q={r['final_q']:.3f} far={r['far_domain_ratio']:.3f} "
                  f"max_rep={r['max_repetition_last_W']} fires={r['detector_fires']} "
                  f"interv={r['intervention_count']}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_seed, arm, s, n_steps, out_dir, registry): s for s in range(n_seeds)}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(f"  [seed={r['seed']}] q={r['final_q']:.3f} far={r['far_domain_ratio']:.3f} "
                      f"max_rep={r['max_repetition_last_W']} fires={r['detector_fires']} "
                      f"interv={r['intervention_count']}", flush=True)
    results.sort(key=lambda r: r["seed"])
    (out_dir / "manifest.json").write_text(
        json.dumps({"arm": arm, "n_seeds": n_seeds, "n_steps": n_steps, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    ap.add_argument("--registry", type=Path,
                    default=ROOT / "experiments" / "registries" / "E_daemon_baseline.json")
    args = ap.parse_args()

    print(f"Modul D batch — calibrated W={W_CAL} M={M_CAL} gran={GRAN_CAL}")
    t0 = time.time()
    for arm in ["meta_baseline", "meta_log_only", "meta_intervention"]:
        run_arm(arm, args.n_seeds, args.n_steps, args.out_root, args.registry, args.workers)
    print(f"\n=== ALL DONE in {time.time()-t0:.0f} s ===")


if __name__ == "__main__":
    main()
