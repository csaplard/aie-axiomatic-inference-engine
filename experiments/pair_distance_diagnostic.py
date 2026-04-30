"""
Diagnosztikai post-hoc: pair-attempt index-távolság a 4 priority karon.

A C kísérlet post-hoc RRR-mintázatára két versengő magyarázat:
  (a) DOMAIN-COHERENCE: a priority a domain-szerkezethez illeszkedik / nem illeszkedik
  (b) CHAIN-ADJACENCY: a magas-priority csúcsok közel vannak / távol egymástól
                       a kauzális gerincben (1, 2, 3, 4 lánc-pozíciók)

Ez a script mind a 4 karra (priority_thesis/uniform/random/inverted)
újrafuttatja a motort SEED=0-val, 2000 think_step-pel, és minden lépés után
rögzíti a (i, j, reject_reason) hármast a `_last_think_snapshot`-ból.

Output: per-kar |i - j| eloszlás (összes próba), és külön a contradicción /
forbidden rejekteltekre.

Nem új tudományos eredmény, csak diagnosztika a D kísérlet tervezéséhez.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from statistics import mean, median, stdev

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine
from experiments.mann_whitney import mann_whitney_u_greater


def _strict_immune_policy(seed: int, log_path: Path) -> Path:
    """Strict-immune policy egy ideiglenes YAML-ben, megegyezik a C kísérlet futási policy-vel."""
    data = {
        "discovery": {
            "enabled": True,
            "ignore_forbidden_edges": False,
            "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "telemetry_log_path": str(log_path) + ".tel",
            "log_path": str(log_path) + ".disc",
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
        }
    }
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


def collect_pair_distances(
    arm_name: str, registry_path: Path, n_steps: int = 2000, seed: int = 0
) -> dict:
    """1 seed-en futtatja a motort, lépésenként rögzíti a párokat."""
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as tf:
        log = Path(tf.name)
    policy = _strict_immune_policy(seed, log)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True,
            policy_path=str(policy),
            registry_path=str(registry_path),
        )
        records = []
        for _ in range(n_steps):
            eng.think_step()
            snap = eng._last_think_snapshot
            if snap.i is None or snap.j is None:
                continue
            records.append({
                "i": int(snap.i),
                "j": int(snap.j),
                "dist": abs(int(snap.i) - int(snap.j)),
                "added": bool(snap.edge_added),
                "reject": snap.edge_reject,
                "mode": snap.mode,
            })
        return {"arm": arm_name, "records": records}
    finally:
        try:
            policy.unlink()
        except OSError:
            pass


def summarize(arm_data: dict) -> dict:
    """Karra: össz, contradiction-rejektelt, forbidden-rejektelt eloszlások."""
    records = arm_data["records"]
    all_dists = [r["dist"] for r in records]
    contra_dists = [r["dist"] for r in records if r["reject"] == "contradiction"]
    forbid_dists = [r["dist"] for r in records if r["reject"] == "forbidden"]
    added_dists = [r["dist"] for r in records if r["added"]]
    immune_dists = contra_dists + forbid_dists

    def _stats(xs: list) -> dict:
        if not xs:
            return {"n": 0, "mean": float("nan"), "median": float("nan"), "stdev": float("nan")}
        return {
            "n": len(xs),
            "mean": mean(xs),
            "median": median(xs),
            "stdev": stdev(xs) if len(xs) > 1 else 0.0,
        }

    return {
        "arm": arm_data["arm"],
        "all": _stats(all_dists),
        "contradiction_rejected": _stats(contra_dists),
        "forbidden_rejected": _stats(forbid_dists),
        "immune_rejected": _stats(immune_dists),
        "successfully_added": _stats(added_dists),
        # Tárolt eloszlások (Mann-Whitney-hez)
        "_all_dists": all_dists,
        "_immune_dists": immune_dists,
    }


def main() -> None:
    arms = {
        "priority_thesis": ROOT / "experiments" / "registries" / "priority_thesis.json",
        "priority_uniform": ROOT / "experiments" / "registries" / "priority_uniform.json",
        "priority_random": ROOT / "experiments" / "registries" / "priority_random.json",
        "priority_inverted": ROOT / "experiments" / "registries" / "priority_inverted.json",
    }
    n_steps = 2000

    print("=" * 78)
    print(f"DIAGNOSTIC: pair-attempt |i - j| eloszlas (seed=0, n_steps={n_steps})")
    print("=" * 78)

    results = {}
    for arm, reg in arms.items():
        print(f"  futtatom: {arm}...")
        data = collect_pair_distances(arm, reg, n_steps=n_steps, seed=0)
        results[arm] = summarize(data)

    print()
    print(f"{'arm':<22} {'all':<24} {'immune-rej.':<22}  {'added':<14}")
    print(f"{'':22} {'mean / med / n':<24} {'mean / med / n':<22}  {'mean / med / n':<14}")
    print("-" * 88)
    for arm, s in results.items():
        a = s["all"]
        ir = s["immune_rejected"]
        ad = s["successfully_added"]
        print(
            f"{arm:<22} "
            f"{a['mean']:>5.2f} / {a['median']:>4.1f} / {a['n']:>5d}    "
            f"{ir['mean']:>5.2f} / {ir['median']:>4.1f} / {ir['n']:>4d}     "
            f"{ad['mean']:>5.2f} / {ad['median']:>4.1f} / {ad['n']:>4d}"
        )

    # Mann-Whitney: az index-távolság eloszlása szignifikánsan eltér-e a kar között?
    print()
    print("Mann-Whitney U összehasonlítás — |i - j| eloszlás (kétoldali p):")
    print("-" * 70)
    arm_list = list(arms.keys())
    for i, a in enumerate(arm_list):
        for b in arm_list[i + 1:]:
            xa = results[a]["_all_dists"]
            xb = results[b]["_all_dists"]
            _, _, p_g = mann_whitney_u_greater(xa, xb)
            _, _, p_l = mann_whitney_u_greater(xb, xa)
            p2 = 2.0 * min(p_g, p_l)
            ma = mean(xa)
            mb = mean(xb)
            print(f"  {a:22s} vs {b:22s}  mean: {ma:>5.2f} vs {mb:>5.2f}  p2={p2:.3e}")

    # Csak az immun-rejektelt esetekre
    print()
    print("Mann-Whitney U összehasonlítás — IMMUN-REJ. |i - j| eloszlás (kétoldali p):")
    print("-" * 70)
    for i, a in enumerate(arm_list):
        for b in arm_list[i + 1:]:
            xa = results[a]["_immune_dists"]
            xb = results[b]["_immune_dists"]
            if not xa or not xb:
                print(f"  {a:22s} vs {b:22s}  (üres minta egyik karon)")
                continue
            _, _, p_g = mann_whitney_u_greater(xa, xb)
            _, _, p_l = mann_whitney_u_greater(xb, xa)
            p2 = 2.0 * min(p_g, p_l)
            ma = mean(xa)
            mb = mean(xb)
            print(f"  {a:22s} vs {b:22s}  mean: {ma:>5.2f} vs {mb:>5.2f}  p2={p2:.3e}  "
                  f"(n_a={len(xa)}, n_b={len(xb)})")


if __name__ == "__main__":
    main()
