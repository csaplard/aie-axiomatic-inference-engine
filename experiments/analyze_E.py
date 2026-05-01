"""
Modul E formal pre-reg verdict-elemzés.

E-H1: BS(class_prior) - BS(L1) > 0.02, MW p < 0.025
E-H2: BS(global) - BS(L1) > 0.01, MW p < 0.025
E-H3: mean(|delta|) > 0.001, Spearman rho > 0.30
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import median, mean, stdev
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.mann_whitney import mann_whitney_u_greater


def spearman_rho(x: list, y: list) -> tuple:
    """Pearson on ranks."""
    n = len(x)
    if n != len(y) or n < 3:
        return float("nan"), float("nan")
    def rank(arr):
        idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and arr[idx[j+1]] == arr[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j+1):
                ranks[idx[k]] = avg
            i = j + 1
        return ranks
    import numpy as np
    rx = np.array(rank(x))
    ry = np.array(rank(y))
    rx_c = rx - rx.mean()
    ry_c = ry - ry.mean()
    denom = math.sqrt((rx_c**2).sum() * (ry_c**2).sum())
    if denom == 0:
        return 0.0, 1.0
    rho = float((rx_c * ry_c).sum() / denom)
    if abs(rho) >= 1.0:
        return rho, 0.0
    z = rho * math.sqrt(n - 2) / math.sqrt(max(1 - rho*rho, 1e-12))
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return rho, float(p)


def main():
    path = ROOT / "experiments" / "runs" / "E_formal" / "formal_results.json"
    results = json.load(open(path, encoding="utf-8"))
    print(f"Records (per seed): {len(results)}")

    # V-feltetelek
    print()
    print("=" * 78)
    print("V-FELTETELEK")
    print("=" * 78)
    n_test_med = median([r["n_test_attempts"] for r in results])
    v1 = n_test_med >= 1000
    print(f"  V1 — total test_attempts >= 1000 medianon: {n_test_med:.0f}  -> {'PASS' if v1 else 'FAIL'}")

    # V2: per-domain-pair coverage. A 4 fő pár (LOGIC×INFO/INFO×LOGIC, QM×NEWTON/NEWTON×QM)
    # mindegyikhez >= 30 attempt (train+test összesen).
    # A run nem rögzíti közvetlenül, de a per_pair_summary-bol látható n_updates per pár.
    all_pair_updates = Counter()
    for r in results:
        for entry in r["per_pair_summary"]:
            key = tuple(entry["key"])
            all_pair_updates[key] += entry["n_updates"]
    main_pairs = [
        ("LOGIC", "INFO"), ("INFO", "LOGIC"),
        ("QM", "Newtoni-mechanika"), ("Newtoni-mechanika", "QM"),
    ]
    main_coverage = [all_pair_updates.get(p, 0) for p in main_pairs]
    v2 = all(c >= 30 * len(results) for c in main_coverage)  # *30 seed
    # Egyszerubben: mindegyik fő pár >= 30 update az összes seed összegezésében
    v2_simple = all(c >= 30 for c in main_coverage)
    print(f"  V2 — 4 fő domain-pár mindegyike >= 30 attempt összesen: "
          f"{dict(zip(main_pairs, main_coverage))}")
    print(f"     -> {'PASS' if v2_simple else 'FAIL'}")

    # V3: class_prior in [0.10, 0.90]
    cps = [r["class_prior"] for r in results]
    cp_med = median(cps)
    v3 = 0.10 <= cp_med <= 0.90
    print(f"  V3 — class_prior median = {cp_med:.3f} in [0.10, 0.90]: {'PASS' if v3 else 'FAIL'}")

    # V4: legalább 1 pár nagyobb távolságra a class_priortol
    deltas_from_05 = []
    for r in results:
        for entry in r["per_pair_summary"]:
            deltas_from_05.append(entry["rule_dist_from_05"])
    max_delta = max(deltas_from_05) if deltas_from_05 else 0
    v4 = max_delta >= 0.05
    print(f"  V4 — max rule distance from 0.5: {max_delta:.3f} >= 0.05: {'PASS' if v4 else 'FAIL'}")

    # ==================== E-H1 ====================
    print()
    print("=" * 78)
    print("E-H1 — BS(class_prior) - BS(L1) > 0.02, MW p < 0.025")
    print("=" * 78)
    h1_lifts = [r["h1_lift"] for r in results]
    bs_l1_list = [r["bs_l1"] for r in results]
    bs_cp_list = [r["bs_class_prior"] for r in results]
    print(f"  L1 BS medians: {median(bs_l1_list):.4f}")
    print(f"  class_prior BS medians: {median(bs_cp_list):.4f}")
    print(f"  h1_lift median: {median(h1_lifts):+.4f}")
    print(f"  h1_lift mean: {mean(h1_lifts):+.4f}")
    print(f"  h1_lift > 0 in {sum(1 for x in h1_lifts if x > 0)}/{len(h1_lifts)} seeds")
    # Mann-Whitney: bs_cp > bs_l1 (egyoldali)
    _, _, p_h1 = mann_whitney_u_greater(bs_cp_list, bs_l1_list)
    print(f"  Mann-Whitney p (egyoldali, BS_class_prior > BS_L1) = {p_h1:.3e}")
    h1_pass = (median(h1_lifts) > 0.02) and (p_h1 < 0.025)
    print(f"  E-H1: {'PASS' if h1_pass else 'FAIL'}")

    # ==================== E-H2 ====================
    print()
    print("=" * 78)
    print("E-H2 — BS(global) - BS(L1) > 0.01, MW p < 0.025")
    print("=" * 78)
    h2_lifts = [r["h2_lift"] for r in results]
    bs_global_list = [r["bs_global"] for r in results]
    print(f"  global BS medians: {median(bs_global_list):.4f}")
    print(f"  h2_lift median: {median(h2_lifts):+.4f}")
    print(f"  h2_lift > 0 in {sum(1 for x in h2_lifts if x > 0)}/{len(h2_lifts)} seeds")
    _, _, p_h2 = mann_whitney_u_greater(bs_global_list, bs_l1_list)
    print(f"  Mann-Whitney p (egyoldali, BS_global > BS_L1) = {p_h2:.3e}")
    h2_pass = (median(h2_lifts) > 0.01) and (p_h2 < 0.025)
    print(f"  E-H2: {'PASS' if h2_pass else 'FAIL'}")

    # ==================== E-H3 ====================
    print()
    print("=" * 78)
    print("E-H3 — mean(|delta|) > 0.001, Spearman rho > 0.30")
    print("=" * 78)
    deltas = [r["mean_abs_delta_train"] for r in results]
    print(f"  mean(|delta|) median: {median(deltas):.4f}")
    delta_pass = median(deltas) > 0.001
    print(f"    > 0.001? {'PASS' if delta_pass else 'FAIL'}")

    # Spearman rho: per-pair (mean_abs_delta) vs (rule_dist_from_05) AGGREGÁLT
    pair_deltas = []
    pair_dists = []
    for r in results:
        for entry in r["per_pair_summary"]:
            pair_deltas.append(entry["mean_abs_delta"])
            pair_dists.append(entry["rule_dist_from_05"])
    rho, p_spearman = spearman_rho(pair_deltas, pair_dists)
    print(f"  Spearman rho (pair_delta vs pair_dist_from_05): {rho:+.3f}, p={p_spearman:.3e}")
    spearman_pass = rho > 0.30
    print(f"    > 0.30? {'PASS' if spearman_pass else 'FAIL'}")
    h3_pass = delta_pass and spearman_pass
    print(f"  E-H3: {'PASS' if h3_pass else 'FAIL'}")

    # ==================== VERDICT ====================
    print()
    print("=" * 78)
    print("E VERDICT (pre-reg dontesfa)")
    print("=" * 78)
    if not (v1 and v2_simple and v3 and v4):
        print("  INVALID_DUE_TO_PRECONDITION")
        return
    if h1_pass and h2_pass and h3_pass:
        print("  MODUL E (egyszerusitett) MEGEROSITVE — predictive coding L1 mukodik,")
        print("  hierarchikus felbontas erteket, update-mechanika aktiv")
    elif h1_pass and not h2_pass and h3_pass:
        print("  RESZLEGES — predikcio mukodik, de domain-par felbontas felesleges")
    elif h1_pass and not h3_pass:
        print("  RESZLEGES — predikcio ad lift-et, de update-magnitudo problema")
    elif not h1_pass:
        print("  CAFOLT — domain-par informacio nem prediktiv")
    else:
        print("  VEGYES — reszleges/teljes ertelmezes szukseges")


if __name__ == "__main__":
    main()
