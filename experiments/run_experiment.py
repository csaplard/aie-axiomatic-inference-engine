"""
Batch experiment runner: N seedet futtat egy registry+policy-on, fix lépésszámmal.

Minden futás:
- Generál egy egyedi telemetria-fájlt experiments/runs/<exp>/seed_<n>.log néven.
- Egyedi ideiglenes policy YAML-t ír (telemetry_log_path + random_seed felülírva).
- Fix max_steps lépésig hív think_step()-et (NINCS Q-küszöb early-exit).
- A telemetria policy szerint minden N lépésben sort ír.

Kimenet: a runs/ alatti telemetria-fájlok, plusz egy manifest.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_policy(
    base_policy_path: Path,
    telemetry_log_path: Path,
    discovery_log_path: Path,
    random_seed: int,
    max_runtime_seconds: float = 0.0,
    strict_immune: bool = False,
) -> Dict[str, Any]:
    with base_policy_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    disc = dict(data.get("discovery") or {})
    disc["telemetry_enabled"] = True
    disc["telemetry_log_path"] = str(telemetry_log_path)
    disc["log_path"] = str(discovery_log_path)
    disc["random_seed"] = int(random_seed)
    disc["max_runtime_seconds"] = float(max_runtime_seconds)
    if strict_immune:
        # forbidden_edges és logical_negation_pairs ténylegesen aktív
        disc["ignore_forbidden_edges"] = False
        disc["ignore_negation_contradictions"] = False
    data["discovery"] = disc
    return data


def _run_one(
    seed: int,
    base_policy: Path,
    registry: Path,
    out_dir: Path,
    max_steps: int,
    telemetry_every_n_steps: Optional[int],
    strict_immune: bool = False,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    telemetry_log = out_dir / f"seed_{seed:04d}.telemetry.log"
    discovery_log = out_dir / f"seed_{seed:04d}.discovery.log"

    policy_data = _build_policy(
        base_policy_path=base_policy,
        telemetry_log_path=telemetry_log,
        discovery_log_path=discovery_log,
        random_seed=seed,
        strict_immune=strict_immune,
    )
    if telemetry_every_n_steps is not None:
        policy_data["discovery"]["telemetry_every_n_steps"] = int(
            telemetry_every_n_steps
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tf:
        yaml.safe_dump(policy_data, tf, allow_unicode=True)
        policy_path = Path(tf.name)

    try:
        from axiom_kernel import AxiomaticInferenceEngine

        engine = AxiomaticInferenceEngine(
            policy_enabled=True,
            policy_path=str(policy_path),
            registry_path=str(registry),
        )
        # Q-küszöb early-exit elkerülése: fix lépésszámú szinkron loop.
        last_q = engine.calculate_q()
        for _ in range(max_steps):
            _, last_q = engine.think_step()

        return {
            "seed": seed,
            "registry": str(registry),
            "max_steps": max_steps,
            "final_q": float(last_q),
            "telemetry_log": str(telemetry_log),
            "discovery_log": str(discovery_log),
        }
    finally:
        try:
            policy_path.unlink()
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch AIE kísérlet-futtató.")
    ap.add_argument("--name", required=True, help="Kísérlet neve (alkönyvtár).")
    ap.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="Regiszter JSON (pl. axioms_registry_timeless.json vagy random kontroll).",
    )
    ap.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "agi_policy_daemon.example.yaml",
        help="Alap policy; csak telemetry/seed mezőket írjuk felül.",
    )
    ap.add_argument("--seeds", type=int, nargs="+", help="Konkrét seedek.")
    ap.add_argument(
        "--n-seeds",
        type=int,
        default=None,
        help="Ha nincs --seeds: 0..n-1 seedek.",
    )
    ap.add_argument("--max-steps", type=int, default=10000)
    ap.add_argument(
        "--telemetry-every",
        type=int,
        default=100,
        help="Hány lépésenként logoljon a telemetria.",
    )
    ap.add_argument("--workers", type=int, default=1, help="Párhuzamos folyamatok.")
    ap.add_argument(
        "--out-root",
        type=Path,
        default=ROOT / "experiments" / "runs",
    )
    ap.add_argument(
        "--strict-immune",
        action="store_true",
        help=(
            "Az immunrendszert MINDIG aktívan tartja: "
            "ignore_forbidden_edges=false, ignore_negation_contradictions=false. "
            "A daemon példa-policy alapból lazítja az immunt; ezzel felülírható."
        ),
    )
    args = ap.parse_args()

    if args.seeds:
        seeds = list(args.seeds)
    elif args.n_seeds is not None:
        seeds = list(range(args.n_seeds))
    else:
        ap.error("Adj meg --seeds vagy --n-seeds értéket.")

    out_dir = args.out_root / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    if args.workers <= 1:
        for s in seeds:
            print(f"[seed={s}] indul...", flush=True)
            r = _run_one(
                s, args.policy, args.registry, out_dir, args.max_steps,
                args.telemetry_every, args.strict_immune,
            )
            results.append(r)
            print(f"[seed={s}] kész — final_q={r['final_q']:.4f}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(
                    _run_one, s, args.policy, args.registry, out_dir,
                    args.max_steps, args.telemetry_every, args.strict_immune,
                ): s
                for s in seeds
            }
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(
                    f"[seed={r['seed']}] kész — final_q={r['final_q']:.4f}",
                    flush=True,
                )

    manifest = {
        "name": args.name,
        "registry": str(args.registry),
        "policy": str(args.policy),
        "max_steps": args.max_steps,
        "telemetry_every": args.telemetry_every,
        "seeds": sorted([r["seed"] for r in results]),
        "runs": sorted(results, key=lambda r: r["seed"]),
    }
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
