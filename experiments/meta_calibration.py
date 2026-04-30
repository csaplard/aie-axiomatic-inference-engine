"""
Modul D — calibration scan.

NEM pre-regisztrált, exploratórikus: paraméter-szken (W, M, granularity)
hogy a stuck-detector firing rate-jének healthy zónáját megtaláljuk.

A formál pre-reg ezekkel a kalibrált paraméterekkel megy.

Cél: olyan (W, M, granularity) kombináció, ahol baseline daemon firing rate
∈ [0.05, 0.30] — sem mindig (false-positive saturation), sem soha (false-negative).
"""

from __future__ import annotations

import json
import sys
import tempfile
from itertools import product
from pathlib import Path
from statistics import mean, median

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


def measure_fire_rate(
    seed: int, n_steps: int, window_size: int, repetition_threshold: int,
    granularity: str, registry: Path, log_dir: Path,
) -> dict:
    """1 seed × n_steps daemon-futás stuck-detector log_only módban."""
    from axiom_kernel import AxiomaticInferenceEngine
    from meta_monitor import StuckDetector

    policy = _build_policy(seed, log_dir)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy), registry_path=str(registry),
        )
        det = StuckDetector(
            window_size=window_size,
            repetition_threshold=repetition_threshold,
            granularity=granularity,
        )
        eng.attach_meta_monitor(det, intervention_mode="log_only")
        for _ in range(n_steps):
            eng.think_step()
        return {
            "seed": seed,
            "fire_count": det.fire_count,
            "attempt_count": det.attempt_count,
            "fire_rate": det.fire_rate(),
            "top_key": det.top_keys(1)[0] if det.top_keys(1) else (None, 0),
        }
    finally:
        policy.unlink(missing_ok=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--n-steps", type=int, default=2000)
    ap.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "experiments" / "registries" / "E_daemon_baseline.json",
    )
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    args = ap.parse_args()

    out_dir = args.out_root / "_meta_calibration"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Paraméter-rács (kis, fókuszált scan)
    W_grid = [50, 100, 200, 500]
    M_grid = [3, 5, 10]
    gran_grid = ["pair", "domain"]

    print(f"=== Modul D calibration scan ===")
    print(f"  registry: {args.registry}")
    print(f"  n_seeds={args.n_seeds}, n_steps={args.n_steps}")
    print(f"  W grid: {W_grid}")
    print(f"  M grid: {M_grid}")
    print(f"  granularity: {gran_grid}")
    print(f"  Cellák száma: {len(W_grid) * len(M_grid) * len(gran_grid)}")
    print()

    results = []
    for W, M, gran in product(W_grid, M_grid, gran_grid):
        cell_results = []
        for seed in range(args.n_seeds):
            r = measure_fire_rate(seed, args.n_steps, W, M, gran, args.registry, out_dir)
            cell_results.append(r)
        fire_rates = [c["fire_rate"] for c in cell_results]
        med = median(fire_rates)
        mn = mean(fire_rates)
        # Klasszifikáció
        if med > 0.95:
            label = "saturated"
        elif med < 0.005:
            label = "silent"
        elif 0.05 <= med <= 0.30:
            label = "healthy"
        else:
            label = "borderline"
        results.append({
            "W": W, "M": M, "granularity": gran,
            "fire_rate_med": med, "fire_rate_mean": mn,
            "label": label,
            "cells": cell_results,
        })
        print(f"  W={W:>4d} M={M:>2d} gran={gran:<6s}  fire_med={med:.3f} fire_mean={mn:.3f}  {label}")

    # Summary tábla
    print()
    print("=" * 78)
    print("HEALTHY ZÓNÁK (fire_rate medián ∈ [0.05, 0.30]):")
    healthy = [r for r in results if r["label"] == "healthy"]
    if not healthy:
        print("  ⚠ NINCS healthy cella — más W/M/granularity kombinációt kell próbálni")
    else:
        for r in healthy:
            print(f"  W={r['W']:>4d} M={r['M']:>2d} gran={r['granularity']:<6s}  "
                  f"fire_med={r['fire_rate_med']:.3f}")

    # JSON output
    out_path = out_dir / "calibration_results.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nMentés: {out_path}")


if __name__ == "__main__":
    main()
