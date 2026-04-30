"""
E kísérlet — hipnagóg üzemmód pre-regisztrált 3-karú batch.

Karok:
  daemon_baseline      — pure daemon, hypnagogic disabled
  hypnagogic_periodic  — every N=300 step trigger entry; full relaxation
  hypnagogic_no_relax  — same trigger timing, but relaxation parameters stay strict
                         (control: tests whether the cyclic reset itself has effect)

Metrikák seedenként:
  - mean RRR  (V1 ellenőrzéséhez)
  - far_domain_edge_ratio  (H1, V2)
  - waking_pass_rate  (H2, V3) — adott élek strict-immune újraértékelés
  - v(N) eloszlás  (H4, V4) — Frobenius path-speed history

Az aggregáció az utórészben:
  - 4 V-feltétel ellenőrzése a daemon_baseline karon
  - Ha bármelyik sérül → INVALID_DUE_TO_SATURATION (a verdict felfüggesztve)
  - Egyébként H1–H4 Mann-Whitney tesztek

Output: experiments/runs/E_<arm>/seed_*.metrics.json + manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Trigger period: hypnagogic episode start every PERIOD steps (only for periodic arms)
PERIOD = 300


def _build_policy(
    arm: str,
    seed: int,
    out_dir: Path,
) -> Path:
    """Policy YAML egy adott karra + seedre. Strict-immune, n_nodes=80,
    hypnagogic enabled csak a két hypnagogic karon."""
    is_periodic = (arm == "hypnagogic_periodic")
    is_no_relax = (arm == "hypnagogic_no_relax")
    is_daemon = (arm == "daemon_baseline")
    # MIND a 3 karon engedélyezzük a hypnagogic policy-t (hogy a fisher_realtime
    # mindenhol fusson, V4 mérhető legyen). A daemon kar sose hív
    # start_hypnagogic_episode()-t, így a state machine AWAKE-ben marad végig.
    hyp_enabled = True
    # daemon és no_relax: relaxation paraméterek strict-szerűek
    if is_daemon or is_no_relax:
        forbidden_weight_deep = 1.0
        far_domain_pref_deep = 0.0
        verify_chain_depth_deep = 1
        negation_threshold_deep = 1.0  # FONTOS: explicit strict, ne defaultolja 0.5-re
    else:  # is_periodic
        forbidden_weight_deep = 0.3
        far_domain_pref_deep = 0.6
        verify_chain_depth_deep = 3
        negation_threshold_deep = 0.5

    data = {
        "discovery": {
            "enabled": True,
            "daemon_mode": True,
            "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False,
            "ignore_negation_contradictions": False,
            "telemetry_enabled": True,
            "telemetry_log_path": str(out_dir / f"seed_{seed:03d}.tel.log"),
            "log_path": str(out_dir / f"seed_{seed:03d}.disc.log"),
            "telemetry_every_n_steps": 100,
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
            "hypnagogic": {
                "enabled": hyp_enabled,
                "entry_steps": 7,
                "deep_steps": 30,
                "exit_steps": 7,
                "cooldown_steps": 200,
                "forbidden_weight_deep": forbidden_weight_deep,
                "far_domain_pref_deep": far_domain_pref_deep,
                "verify_chain_depth_deep": verify_chain_depth_deep,
                "negation_threshold_deep": negation_threshold_deep,
                "fisher_trigger_factor": 2.0,
                "fisher_min_history": 20,
                "log_path": str(out_dir / f"seed_{seed:03d}.hypnagogic.jsonl"),
            },
        }
    }
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


def _compute_pass_rate(eng, edges_added) -> float:
    """Strict-immune újraértékelés: hány a hozzáadott élekből lenne elfogadható?
    Pass = NOT forbidden ÉS van legalább 1 közbülső csúcs (verify_logic depth-1)."""
    if not edges_added:
        return float("nan")
    if eng._registry is None:
        return float("nan")
    fbe = eng._registry.forbidden_edges
    pass_count = 0
    A = eng.knowledge_matrix
    for (i, j) in edges_added:
        # 1. Forbidden check
        if (i, j) in fbe:
            continue
        # 2. Contradiction check (path i → ... → neg(j), excluding (i, j) itself)
        neg_j = eng._negation.get(j)
        contradicts = False
        if neg_j is not None:
            # Temporarily exclude (i, j) edge, check path
            old = A[i, j]
            A[i, j] = 0.0
            contradicts = eng._has_path_unlocked(A, i, neg_j)
            A[i, j] = old
        if contradicts:
            continue
        # 3. Verify_logic depth-1: van k melyre A[i, k] > 0 ÉS A[k, j] > 0 (kivéve (i, j) önmagát)
        # Mátrix-szorzás trükk: van-e k != i, j melyre A[i, k] > 0 és A[k, j] > 0
        intermediates = np.where((A[i, :] > 0) & (A[:, j] > 0))[0]
        # ki kell zárnunk a saját csúcsokat
        intermediates = [k for k in intermediates if k != i and k != j]
        if len(intermediates) == 0:
            continue
        pass_count += 1
    return float(pass_count) / float(len(edges_added))


def _compute_far_domain_ratio(eng, edges_added) -> float:
    """Mennyi az élek aránya, amelyekre domain(i) ≠ domain(j)?"""
    if not edges_added or eng._registry is None:
        return float("nan")
    far_count = 0
    for (i, j) in edges_added:
        di = eng.axiom_labels.get(i)
        dj = eng.axiom_labels.get(j)
        if di is not None and dj is not None and di != dj:
            far_count += 1
    return float(far_count) / float(len(edges_added))


def run_seed(arm: str, seed: int, n_steps: int, out_dir: Path) -> dict:
    """Egy seed futtatása."""
    policy = _build_policy(arm, seed, out_dir)
    try:
        from axiom_kernel import AxiomaticInferenceEngine

        registry = ROOT / "experiments" / "registries" / f"E_{arm}.json"
        eng = AxiomaticInferenceEngine(
            policy_enabled=True,
            policy_path=str(policy),
            registry_path=str(registry),
        )
        # Snapshot of initial edges
        A0 = eng.knowledge_matrix.copy()

        # Run with periodic hypnagogic triggers (if applicable)
        is_hypnagogic = arm in ("hypnagogic_periodic", "hypnagogic_no_relax")
        for step in range(n_steps):
            # Periodic trigger: every PERIOD steps, attempt to start a hypnagogic episode
            if is_hypnagogic and step > 0 and step % PERIOD == 0:
                eng.start_hypnagogic_episode()  # only succeeds if AWAKE
            eng.think_step()

        # Compute metrics
        A = eng.knowledge_matrix
        n = A.shape[0]
        # Edges added during run: A > 0 ÉS A0 == 0 (i != j)
        diff = (A > 0) & (A0 == 0)
        np.fill_diagonal(diff, False)
        edges_added = list(zip(*np.where(diff)))
        edges_added_int = [(int(i), int(j)) for (i, j) in edges_added]

        # Pass-rate: strict-immune re-evaluation
        pass_rate = _compute_pass_rate(eng, edges_added_int)
        # Far-domain ratio
        far_domain_ratio = _compute_far_domain_ratio(eng, edges_added_int)
        # Mean RRR from telemetry log
        from experiments.aggregate import _parse_log
        tel_path = out_dir / f"seed_{seed:03d}.tel.log"
        parsed = _parse_log(tel_path)
        rrr_values = [v["rrr"] for v in parsed.values() if not np.isnan(v["rrr"])]
        mean_rrr = float(np.mean(rrr_values)) if rrr_values else float("nan")
        # v(N) history (from FisherRealtime _history deque)
        if eng._fisher_realtime is not None:
            vn_history = list(eng._fisher_realtime._history)
            # 4 alternatív metrika (csak a végállapotra; gyors, ablakszélességű egy snapshot)
            alt_metrics = eng._fisher_realtime.compute_alt_metrics() or {}
        else:
            vn_history = []
            alt_metrics = {}

        return {
            "arm": arm,
            "seed": seed,
            "n_edges_added": len(edges_added_int),
            "mean_rrr": mean_rrr,
            "far_domain_ratio": far_domain_ratio,
            "waking_pass_rate": pass_rate,
            "vn_mean": float(np.mean(vn_history)) if vn_history else float("nan"),
            "vn_std": float(np.std(vn_history)) if vn_history else float("nan"),
            "vn_history_len": len(vn_history),
            "alt_frobenius": alt_metrics.get("frobenius", float("nan")),
            "alt_spectral_gap": alt_metrics.get("spectral_gap", float("nan")),
            "alt_row_entropy_diff": alt_metrics.get("row_entropy_diff", float("nan")),
            "alt_kl": alt_metrics.get("kl", float("nan")),
        }
    finally:
        policy.unlink(missing_ok=True)


def run_arm(
    arm: str, n_seeds: int, n_steps: int, out_root: Path, workers: int = 4
) -> list:
    """Egy kar futtatása párhuzamosan."""
    out_dir = out_root / f"E_{arm}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== arm: {arm} ({n_seeds} seed × {n_steps} steps, {workers} workers) ===")

    results = []
    if workers <= 1:
        for seed in range(n_seeds):
            r = run_seed(arm, seed, n_steps, out_dir)
            results.append(r)
            print(f"  [seed={seed}] edges={r['n_edges_added']} rrr={r['mean_rrr']:.3f} "
                  f"far={r['far_domain_ratio']:.3f} pass={r['waking_pass_rate']:.3f} "
                  f"vn={r['vn_mean']:.3f}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {
                ex.submit(run_seed, arm, seed, n_steps, out_dir): seed
                for seed in range(n_seeds)
            }
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(f"  [seed={r['seed']}] edges={r['n_edges_added']} rrr={r['mean_rrr']:.3f} "
                      f"far={r['far_domain_ratio']:.3f} pass={r['waking_pass_rate']:.3f} "
                      f"vn={r['vn_mean']:.3f}", flush=True)

    results.sort(key=lambda r: r["seed"])
    manifest = {"arm": arm, "n_seeds": n_seeds, "n_steps": n_steps, "results": results}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    ap.add_argument("--arms", nargs="+", default=[
        "daemon_baseline", "hypnagogic_periodic", "hypnagogic_no_relax",
    ])
    args = ap.parse_args()

    t0 = time.time()
    all_results = {}
    for arm in args.arms:
        all_results[arm] = run_arm(
            arm, args.n_seeds, args.n_steps, args.out_root, args.workers
        )
    elapsed = time.time() - t0
    print(f"\n=== ALL DONE in {elapsed:.0f} s ===")


if __name__ == "__main__":
    main()
