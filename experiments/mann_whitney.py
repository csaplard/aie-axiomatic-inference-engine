"""
Mann-Whitney U teszt: a timeless kar TOPO-eloszlása
SZIGNIFIKÁNSAN nagyobb-e mint mindhárom kontroll karé?

Egyoldali (greater) teszt minden timeless-vs-control párra. Bonferroni-korrekció
a többszörös tesztelésre. Csak stdlib (math) — nincs scipy függőség.

Implementáció:
- Rangsor (átlagolt rang ties esetén)
- U statisztika
- Normál közelítés (n>=20-ra biztonságos)
- Egyoldali p-érték (greater)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import List, Tuple

from experiments.aggregate import _parse_log


def _final_metric_values(manifest_path: Path, metric: str) -> List[float]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    out: List[float] = []
    for run in manifest["runs"]:
        parsed = _parse_log(Path(run["telemetry_log"]))
        if not parsed:
            continue
        last_tick = max(parsed.keys())
        out.append(parsed[last_tick][metric])
    return out


def _final_topo_values(manifest_path: Path) -> List[float]:
    return _final_metric_values(manifest_path, "topo")


def _ranks_with_ties(values: List[float]) -> Tuple[List[float], float]:
    """Visszaadja a rangokat (átlagolva ties esetén) és a tie-correction T-t."""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    n = len(values)
    ranks = [0.0] * n
    tie_term = 0.0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        t = j - i + 1
        if t > 1:
            tie_term += (t ** 3 - t)
        i = j + 1
    return ranks, tie_term


def mann_whitney_u_greater(
    a: List[float], b: List[float]
) -> Tuple[float, float, float]:
    """
    Egyoldali Mann-Whitney U: H1: a > b (a karok összevont rangjai alapján).
    Visszaadja: (U_a, z, p_one_sided).
    """
    if not a or not b:
        return float("nan"), float("nan"), float("nan")
    n1, n2 = len(a), len(b)
    pooled = a + b
    ranks, tie_term = _ranks_with_ties(pooled)
    R1 = sum(ranks[:n1])
    U1 = R1 - n1 * (n1 + 1) / 2.0
    mean_U = n1 * n2 / 2.0
    n = n1 + n2
    var_U = (n1 * n2 / 12.0) * ((n + 1) - tie_term / (n * (n - 1)))
    if var_U <= 0:
        return U1, float("nan"), float("nan")
    z = (U1 - mean_U) / math.sqrt(var_U)
    # H1: a > b ->magas U1 felső farok p
    # Egyoldali p = 1 - Phi(z); folytonos korrekció nélkül (n>=20-ra elég)
    p = 0.5 * math.erfc(z / math.sqrt(2.0))
    return U1, z, p


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Mann-Whitney U: timeless TOPO > kontroll-karok TOPO?"
    )
    ap.add_argument("--timeless-manifest", type=Path, required=True)
    ap.add_argument(
        "--control-manifest", type=Path, action="append", required=True,
        help="Egy vagy több kontroll-manifest (random, no_immune, random_immune).",
    )
    ap.add_argument(
        "--alpha", type=float, default=0.01,
        help="Szignifikancia-szint Bonferroni-korrekció ELŐTT (alap: 0.01).",
    )
    ap.add_argument(
        "--metric", choices=["topo", "q", "asym", "rrr"], default="topo",
        help="Melyik metrika végértékét vessük össze.",
    )
    ap.add_argument(
        "--direction", choices=["greater", "less"], default="greater",
        help=(
            "H1: greater = timeless > kontroll (default, TOPO-hoz); "
            "less = timeless < kontroll (Q-hoz, ahol az immun csökkenti az élsűrűséget)."
        ),
    )
    args = ap.parse_args()

    metric = args.metric
    direction = args.direction
    timeless = _final_metric_values(args.timeless_manifest, metric)
    n_tests = len(args.control_manifest)
    bonf_alpha = args.alpha / n_tests
    metric_u = metric.upper()
    sign = ">" if direction == "greater" else "<"

    print()
    print("=" * 78)
    print(f"MANN-WHITNEY U: timeless {metric_u} {sign} kontrollok {metric_u} (egyoldali)")
    print(f"  alpha={args.alpha}, Bonferroni-korr ({n_tests} teszt) ->alpha'={bonf_alpha:.4g}")
    print("=" * 78)
    print(
        f"  timeless: n={len(timeless)}, median {metric_u}_final="
        f"{median(timeless) if timeless else float('nan'):.4f}"
    )
    print()
    all_pass = True
    for cm in args.control_manifest:
        with cm.open(encoding="utf-8") as f:
            arm_name = json.load(f)["name"]
        ctrl = _final_metric_values(cm, metric)
        if direction == "greater":
            U, z, p = mann_whitney_u_greater(timeless, ctrl)
        else:
            U, z, p = mann_whitney_u_greater(ctrl, timeless)
        med = median(ctrl) if ctrl else float("nan")
        passed = (not math.isnan(p)) and p < bonf_alpha
        all_pass = all_pass and passed
        marker = "PASS" if passed else "FAIL"
        print(
            f"[{marker}] vs {arm_name:<28} n={len(ctrl):>3}  median={med:>7.4f}  "
            f"U={U:>7.1f}  z={z:>6.2f}  p={p:.3e}"
        )

    print()
    print("-" * 78)
    if all_pass:
        print(
            f"VÉGEREDMÉNY: timeless {metric_u} {sign} minden kontroll {metric_u}-nál"
            f" szignifikánsan (alpha'={bonf_alpha:.4g} szinten)."
        )
    else:
        print(
            f"VÉGEREDMÉNY: legalább egy kontroll {metric_u}-eloszlása nem különbözik"
            " szignifikánsan a kívánt irányban."
        )
    print("-" * 78)


if __name__ == "__main__":
    main()
