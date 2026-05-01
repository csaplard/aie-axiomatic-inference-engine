"""
Modul E (egyszerűsített) — confound-scan + formal pre-reg batch.

mode=confound: α-szken (4 érték × 3 seed × 2000 step) → healthy zone validáció
mode=formal:   30 seed × 2000 step (1000 train + 1000 test, frozen rules) →
               E-H1, E-H2, E-H3 verdict
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, median

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


def run_seed(seed: int, n_steps: int, alpha: float, registry: Path, log_dir: Path,
             train_fraction: float = 0.5) -> dict:
    """1 seed: AIE futtatás, L1RuleSet és GlobalRule observe, train/test split."""
    from axiom_kernel import AxiomaticInferenceEngine
    from predictive_layer import L1RuleSet, GlobalRule, brier_score

    policy = _build_policy(seed, log_dir)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy), registry_path=str(registry),
        )
        rs = L1RuleSet(alpha=alpha, init_value=0.5)
        gr = GlobalRule(alpha=alpha, init_value=0.5)
        eng.attach_predictive_layer(l1_rules=rs, global_rule=gr)

        n_train = int(n_steps * train_fraction)
        # TRAIN fázis: rules update
        for _ in range(n_train):
            eng.think_step()
        # FREEZE
        rs.freeze()
        gr.freeze()
        # End-of-train state snapshot
        train_rules = rs.all_rules()
        train_global = gr.value
        train_updates = rs.total_updates()

        # TEST fázis: rules frozen, predictions collected
        l1_predictions = []
        global_predictions = []
        actuals = []
        domain_keys_test = []
        for step in range(n_train, n_steps):
            # MIELŐTT az engine megpróbálja az élt — ha lesz pár, predikciót adunk
            # A legtisztább: lépünk think_step-et, nézzük a snapshot-ot, és számoljuk a predikciót
            # a már frozen rule-okkal
            eng.think_step()
            snap = eng._last_think_snapshot
            if snap.i is None or snap.j is None:
                continue
            if snap.mode == "idle_sparse":
                continue
            # Triviális rejekt-eket kihagyjuk
            if (not snap.edge_added) and (snap.edge_reject == "exists"):
                continue
            d_a = eng.axiom_labels.get(int(snap.i))
            d_b = eng.axiom_labels.get(int(snap.j))
            l1_pred = rs.predict(d_a, d_b)
            g_pred = gr.predict(d_a, d_b)
            actual = 1 if snap.edge_added else 0
            l1_predictions.append(l1_pred)
            global_predictions.append(g_pred)
            actuals.append(actual)
            from predictive_layer import _domain_key
            domain_keys_test.append((_domain_key(d_a), _domain_key(d_b)))

        # Class-prior baseline = train fázis átlagos accept-rate
        # (Kiszámítható a train_global-ból, ami pont az accept-rate; vagy explicit)
        # GlobalRule(alpha) train-en végén = EMA-átlag, ami közelíti a class-priort
        # Tisztább: használjuk train_global-t mint class-prior baseline.
        class_prior = train_global

        # Brier scores
        bs_l1 = brier_score(l1_predictions, actuals) if actuals else float("nan")
        bs_global = brier_score(global_predictions, actuals) if actuals else float("nan")
        bs_class_prior = brier_score(
            [class_prior] * len(actuals), actuals
        ) if actuals else float("nan")

        # H1 lift: BS(class_prior) - BS(L1)
        h1_lift = bs_class_prior - bs_l1
        # H2 specificity-lift: BS(global) - BS(L1)
        h2_lift = bs_global - bs_l1

        # H3 update magnitudes per pair (a train fázis update_history-jából)
        update_hist = rs.update_history()
        deltas_per_pair = {}
        for key, pre, post, delta in update_hist:
            deltas_per_pair.setdefault(key, []).append(abs(delta))
        mean_abs_delta = (
            mean(d for ds in deltas_per_pair.values() for d in ds)
            if deltas_per_pair else 0.0
        )

        # H3 Spearman: per-pair update magnitude vs |0.5 - prior|
        # prior = class-rate, közelítjük a train-végi global rule-lal
        per_pair_summary = []
        for key, deltas in deltas_per_pair.items():
            if deltas:
                avg_d = mean(deltas)
                rule_dist = abs(0.5 - train_rules.get(key, 0.5))
                per_pair_summary.append({"key": list(key), "mean_abs_delta": avg_d,
                                          "rule_dist_from_05": rule_dist,
                                          "n_updates": len(deltas)})

        # Outcome eloszlás for V-conditions
        from collections import Counter
        c = Counter(actuals)
        accept_rate_test = c.get(1, 0) / max(len(actuals), 1)

        return {
            "seed": seed,
            "alpha": alpha,
            "n_test_attempts": len(actuals),
            "accept_rate_test": accept_rate_test,
            "class_prior": class_prior,
            "bs_l1": bs_l1,
            "bs_global": bs_global,
            "bs_class_prior": bs_class_prior,
            "h1_lift": h1_lift,
            "h2_lift": h2_lift,
            "mean_abs_delta_train": mean_abs_delta,
            "per_pair_summary": per_pair_summary,
            "train_updates": train_updates,
            "n_unique_pairs": len(train_rules),
        }
    finally:
        policy.unlink(missing_ok=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["confound", "formal"], default="formal")
    ap.add_argument("--n-seeds", type=int, default=30)
    ap.add_argument("--n-steps", type=int, default=2000)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--registry", type=Path,
        default=ROOT / "experiments" / "registries" / "C2_domain_negation.json",
    )
    ap.add_argument("--out-root", type=Path, default=ROOT / "experiments" / "runs")
    args = ap.parse_args()

    if args.mode == "confound":
        # 4 alpha × 3 seed
        alphas = [0.05, 0.10, 0.20, 0.30]
        seeds = [0, 1, 2]
        out_dir = args.out_root / "E_confound"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"=== Modul E confound-scan: {len(alphas)} alpha × {len(seeds)} seed ===")
        all_results = []
        for alpha in alphas:
            for seed in seeds:
                r = run_seed(seed, args.n_steps, alpha, args.registry, out_dir)
                all_results.append(r)
                print(f"  alpha={alpha:.2f} seed={seed}  bs_l1={r['bs_l1']:.4f}  "
                      f"bs_class={r['bs_class_prior']:.4f}  h1_lift={r['h1_lift']:+.4f}  "
                      f"accept_test={r['accept_rate_test']:.3f}", flush=True)
        # Aggregate per alpha
        print()
        print("Confound-térkép összegzés:")
        for alpha in alphas:
            cells = [r for r in all_results if r["alpha"] == alpha]
            h1_med = median([c["h1_lift"] for c in cells])
            bs_med = median([c["bs_l1"] for c in cells])
            ar_med = median([c["accept_rate_test"] for c in cells])
            print(f"  alpha={alpha:.2f}  h1_lift_med={h1_med:+.4f}  bs_l1_med={bs_med:.4f}  "
                  f"accept_med={ar_med:.3f}")
        with (out_dir / "confound_results.json").open("w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=1)
    else:
        # Formal: 30 seed × n_steps × egyetlen alpha
        out_dir = args.out_root / "E_formal"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"=== Modul E formal: {args.n_seeds} seed × {args.n_steps} step × alpha={args.alpha} ===")
        t0 = time.time()
        results = []
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(run_seed, s, args.n_steps, args.alpha, args.registry, out_dir): s
                for s in range(args.n_seeds)
            }
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(f"  [seed={r['seed']}] bs_l1={r['bs_l1']:.4f}  "
                      f"h1_lift={r['h1_lift']:+.4f}  h2_lift={r['h2_lift']:+.4f}  "
                      f"delta={r['mean_abs_delta_train']:.4f}", flush=True)
        results.sort(key=lambda r: r["seed"])
        print(f"\n=== {time.time()-t0:.0f} s ===")
        with (out_dir / "formal_results.json").open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
