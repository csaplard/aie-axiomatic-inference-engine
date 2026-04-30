"""
Modul B — pre-regisztrált batch runner: B-Determinism + B-Continuity.

3 procedure × 30 seed × n_nodes=80 × 2*5000 lépés:

  Procedure A (continuous): seed=k, 10000 lépés folytonosan
  Procedure B-full (B-Determinism): seed=k, 5000 lépés → save_rng=True →
    új engine instance → load → 5000 további lépés
    Várt: A_A == A_B (bitre)
  Procedure B-partial (B-Continuity): seed=k, 5000 lépés → save_rng=False →
    új engine instance → load → új seed (k+1000) → 5000 további lépés
    Várt: ||A_A - A_Bp||_F << ||A_A - A_C||_F (lényeges folytonosság)
  Procedure C (fresh, kontroll): seed=k+1000, 10000 lépés
    Független baseline a B-partial-hoz

Output: experiments/runs/M/seed_*.metrics.json + manifest.json
"""

from __future__ import annotations

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


def _build_policy(seed: int, log_dir: Path) -> Path:
    """Minimális policy: strict immune, n_nodes registry-ből, hipnagóg KIKAPCS."""
    data = {
        "discovery": {
            "enabled": True,
            "daemon_mode": True,
            "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False,
            "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "telemetry_log_path": str(log_dir / f"seed_{seed:03d}.tel"),
            "log_path": str(log_dir / f"seed_{seed:03d}.disc"),
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
            "hypnagogic": {"enabled": False},
        }
    }
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


def _new_engine(policy_path: Path, registry: Path):
    from axiom_kernel import AxiomaticInferenceEngine
    return AxiomaticInferenceEngine(
        policy_enabled=True,
        policy_path=str(policy_path),
        registry_path=str(registry),
    )


def run_one_seed(seed: int, n_steps_half: int, work_dir: Path, registry: Path) -> dict:
    """Egy seed-en a 4 procedure (A, B-full, B-partial, C) futtatása."""
    out_dir = work_dir / f"seed_{seed:03d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    mem_dir = out_dir / "memory"

    # ============== Procedure A: continuous ==============
    policy_a = _build_policy(seed, out_dir)
    try:
        eng_a = _new_engine(policy_a, registry)
        for _ in range(2 * n_steps_half):
            eng_a.think_step()
        A_A = eng_a.knowledge_matrix.copy()
    finally:
        policy_a.unlink(missing_ok=True)

    # ============== Procedure B-full (B-Determinism) ==============
    policy_b = _build_policy(seed, out_dir)
    try:
        eng_b1 = _new_engine(policy_b, registry)
        for _ in range(n_steps_half):
            eng_b1.think_step()
        eng_b1.save_state(mem_dir, "checkpoint_full", save_rng=True)

        # Új engine, load, folytatás
        eng_b2 = _new_engine(policy_b, registry)
        ok_full = eng_b2.load_state(mem_dir, "checkpoint_full")
        for _ in range(n_steps_half):
            eng_b2.think_step()
        A_Bfull = eng_b2.knowledge_matrix.copy()
    finally:
        policy_b.unlink(missing_ok=True)

    # ============== Procedure B-partial (B-Continuity) ==============
    policy_bp_first = _build_policy(seed, out_dir)
    try:
        eng_bp1 = _new_engine(policy_bp_first, registry)
        for _ in range(n_steps_half):
            eng_bp1.think_step()
        eng_bp1.save_state(mem_dir, "checkpoint_partial", save_rng=False)
    finally:
        policy_bp_first.unlink(missing_ok=True)

    # Új engine új seed-del, load (RNG nélkül), folytatás
    new_seed = seed + 1000
    policy_bp_second = _build_policy(new_seed, out_dir)
    try:
        eng_bp2 = _new_engine(policy_bp_second, registry)
        ok_partial = eng_bp2.load_state(mem_dir, "checkpoint_partial")
        for _ in range(n_steps_half):
            eng_bp2.think_step()
        A_Bpartial = eng_bp2.knowledge_matrix.copy()
    finally:
        policy_bp_second.unlink(missing_ok=True)

    # ============== Procedure C: fresh, új seed (kontroll) ==============
    policy_c = _build_policy(new_seed, out_dir)
    try:
        eng_c = _new_engine(policy_c, registry)
        for _ in range(2 * n_steps_half):
            eng_c.think_step()
        A_C = eng_c.knowledge_matrix.copy()
    finally:
        policy_c.unlink(missing_ok=True)

    # ============== Metrikák ==============
    def frob(X, Y):
        return float(np.linalg.norm(X - Y, ord="fro"))

    def edges_set(M):
        np.fill_diagonal(M, 0.0)  # kizárjuk a diagonálist
        idx = np.where(M > 0)
        return frozenset(zip(idx[0].tolist(), idx[1].tolist()))

    def jaccard(M1, M2):
        E1 = edges_set(M1.copy())
        E2 = edges_set(M2.copy())
        if not E1 and not E2:
            return 1.0
        return len(E1 & E2) / max(len(E1 | E2), 1)

    return {
        "seed": seed,
        "B_determinism_frob": frob(A_A, A_Bfull),
        "B_determinism_passed": bool(np.allclose(A_A, A_Bfull, atol=1e-10)),
        "d_AB": frob(A_A, A_Bpartial),
        "d_AC": frob(A_A, A_C),
        "ratio_dAB_dAC": frob(A_A, A_Bpartial) / max(frob(A_A, A_C), 1e-9),
        "J_AB": jaccard(A_A, A_Bpartial),
        "J_AC": jaccard(A_A, A_C),
        "n_edges_A": int(np.count_nonzero(A_A) - A_A.shape[0]),
        "n_edges_C": int(np.count_nonzero(A_C) - A_C.shape[0]),
        "load_full_ok": bool(ok_full),
        "load_partial_ok": bool(ok_partial),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps-half", type=int, default=5000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    ap.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "experiments" / "registries" / "E_daemon_baseline.json",
    )
    args = ap.parse_args()

    out_dir = args.out_root / "M"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Modul B batch ({args.n_seeds} seed × 2x{args.n_steps_half} steps) ===")
    print(f"  registry: {args.registry}")
    t0 = time.time()
    results = []
    if args.workers <= 1:
        for seed in range(args.n_seeds):
            r = run_one_seed(seed, args.n_steps_half, out_dir, args.registry)
            results.append(r)
            print(
                f"  [seed={seed}] B-det frob={r['B_determinism_frob']:.4f} "
                f"d_AB={r['d_AB']:.2f} d_AC={r['d_AC']:.2f} "
                f"ratio={r['ratio_dAB_dAC']:.3f}", flush=True
            )
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(run_one_seed, s, args.n_steps_half, out_dir, args.registry): s
                for s in range(args.n_seeds)
            }
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(
                    f"  [seed={r['seed']}] B-det frob={r['B_determinism_frob']:.4f} "
                    f"d_AB={r['d_AB']:.2f} d_AC={r['d_AC']:.2f} "
                    f"ratio={r['ratio_dAB_dAC']:.3f}", flush=True
                )
    results.sort(key=lambda r: r["seed"])
    elapsed = time.time() - t0
    print(f"\n=== DONE in {elapsed:.0f} s ===")

    manifest = {
        "n_seeds": args.n_seeds,
        "n_steps_half": args.n_steps_half,
        "registry": str(args.registry),
        "results": results,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
