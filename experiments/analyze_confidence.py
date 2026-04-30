"""
Modul C — formal batch verdict-elemzés.

Bemenet:
  experiments/runs/C_calibrate/calibration.json — Q1, Q2, Q3, surprise_median
  experiments/runs/C_formal/edge_records.json   — ~27000 él

Tesztek:
  V1-V4 érvényesség-feltételek
  C-H1: Mann-Whitney U a near_contradiction vs proven contradiction-rate-jén
  C-H2: Spearman ρ confidence_score vs waking_pass_strict
  Incremental R²: confidence_score additív magyarázó ereje

A 0.02-0.05 közti gray zone külön kategóriaként.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median, stdev

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.mann_whitney import mann_whitney_u_greater
from confidence_score import epistemic_label


def spearman_rho(x: list, y: list) -> tuple:
    """Pearson korreláció a rangokon. Visszaadja: (rho, p_two_sided_normal_approx)."""
    n = len(x)
    if n != len(y) or n < 3:
        return float("nan"), float("nan")
    # Ranks (avg for ties)
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
    rx = np.array(rank(x))
    ry = np.array(rank(y))
    # Pearson on ranks
    rx_c = rx - rx.mean()
    ry_c = ry - ry.mean()
    denom = math.sqrt((rx_c**2).sum() * (ry_c**2).sum())
    if denom == 0:
        return 0.0, 1.0
    rho = float((rx_c * ry_c).sum() / denom)
    # Normal approximation for two-sided p
    if abs(rho) >= 1.0:
        return rho, 0.0
    z = rho * math.sqrt(n - 2) / math.sqrt(max(1 - rho*rho, 1e-12))
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return rho, float(p)


def regress(X: np.ndarray, y: np.ndarray) -> tuple:
    """OLS regresszió: visszaadja (R^2, residual_variance)."""
    # X: (n, k) features (with bias column)
    # y: (n,)
    # OLS: beta = (X^T X)^-1 X^T y
    try:
        beta, residuals, rank_, sv = np.linalg.lstsq(X, y, rcond=None)
        y_pred = X @ beta
        ss_res = float(((y - y_pred) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / max(ss_tot, 1e-12)
        return r2, ss_res
    except np.linalg.LinAlgError:
        return float("nan"), float("nan")


def main():
    cal_path = ROOT / "experiments" / "runs" / "C_calibrate" / "calibration.json"
    edge_path = ROOT / "experiments" / "runs" / "C_formal" / "edge_records.json"
    cal = json.load(open(cal_path, encoding="utf-8"))
    records = json.load(open(edge_path, encoding="utf-8"))

    print(f"Calibration: Q1={cal['confidence_q1']:.3f}, Q2={cal['confidence_q2']:.3f}, "
          f"Q3={cal['confidence_q3']:.3f}, surprise_median={cal['surprise_median']:.3f}")
    print(f"Formal records: {len(records)}")

    # Cimkezes
    q1, q2, q3 = cal["confidence_q1"], cal["confidence_q2"], cal["confidence_q3"]
    surp_med = cal["surprise_median"]
    for r in records:
        r["label"] = epistemic_label(
            r["confidence_score"], r["surprise_raw"], q1, q2, q3, surp_med,
        )

    # V-feltetelek
    print()
    print("=" * 78)
    print("V-FELTETELEK")
    print("=" * 78)
    label_counter = Counter(r["label"] for r in records)
    print(f"  Cimke-eloszlas: {dict(label_counter)}")
    n_total = len(records)
    v2_pass = all(label_counter[lbl] / n_total >= 0.05 for lbl in ["proven", "near_contradiction"])
    print(f"  V2: minden donto cimke (proven, near_contradiction) >= 5%: {'PASS' if v2_pass else 'FAIL (cimke uresen marad)'}")
    # Var: ha hypothesis ures, az nem szamit kotelezo V2 cella, csak donto
    print(f"     proven: {label_counter['proven']/n_total:.3f}  near_contradiction: {label_counter['near_contradiction']/n_total:.3f}")
    print(f"     hypothesis: {label_counter['hypothesis']/n_total:.3f}  uncertain: {label_counter['uncertain']/n_total:.3f}")

    # V3: legalabb 1 input variancia > 0
    cd_var = np.var([r["chain_depth_score"] for r in records])
    si_var = np.var([r["surprise_inverse_score"] for r in records])
    sh_var = np.var([r["stuck_history_score"] for r in records])
    cdi_var = np.var([r["contradiction_distance_score"] for r in records])
    v3_pass = max(cd_var, si_var, sh_var, cdi_var) > 0
    print(f"  V3: legalabb 1 input var > 0: chain_depth={cd_var:.4f}, "
          f"surprise={si_var:.4f}, stuck={sh_var:.4f}, contra_dist={cdi_var:.4f}")
    print(f"     -> {'PASS' if v3_pass else 'FAIL'}")

    # V4: kollinearitás chain_depth és surprise között
    cd = np.array([r["chain_depth_score"] for r in records])
    si = np.array([r["surprise_inverse_score"] for r in records])
    if cd.std() > 0 and si.std() > 0:
        rho_cd_si = float(np.corrcoef(cd, si)[0, 1])
    else:
        rho_cd_si = 0.0
    v4_pass = abs(rho_cd_si) < 0.7
    print(f"  V4: |rho(chain_depth, surprise)| < 0.7: {abs(rho_cd_si):.3f}  -> {'PASS' if v4_pass else 'FAIL'}")

    # ==================== C-H1 ====================
    print()
    print("=" * 78)
    print("C-H1 — near_contradiction cimke prediktiv (vs proven)")
    print("=" * 78)
    near = [r for r in records if r["label"] == "near_contradiction"]
    proven = [r for r in records if r["label"] == "proven"]
    near_contr = [int(r["is_in_contradiction"]) for r in near]
    proven_contr = [int(r["is_in_contradiction"]) for r in proven]
    print(f"  near_contradiction: n={len(near)}, contradiction-rate={sum(near_contr)/max(len(near),1):.3f}")
    print(f"  proven:             n={len(proven)}, contradiction-rate={sum(proven_contr)/max(len(proven),1):.3f}")
    if near and proven:
        _, _, p_h1 = mann_whitney_u_greater(near_contr, proven_contr)
        rate_diff = sum(near_contr)/len(near) - sum(proven_contr)/len(proven)
        print(f"  Mann-Whitney p (egyoldali, near > proven) = {p_h1:.3e}")
        print(f"  rate-difference = {rate_diff:.3f} (kuszob: >=0.10)")
        h1_pass = (p_h1 < 0.025) and (rate_diff >= 0.10)
        print(f"  C-H1: {'PASS' if h1_pass else 'FAIL'}")
    else:
        print(f"  C-H1: NEM ERTEKELHETO (egyik kategoria ures)")

    # ==================== C-H2 ====================
    print()
    print("=" * 78)
    print("C-H2 — confidence_score korrelal a waking_pass-szal")
    print("=" * 78)
    confs = [r["confidence_score"] for r in records]
    waking = [int(r["waking_pass_strict"]) for r in records]
    rho, p_h2 = spearman_rho(confs, waking)
    print(f"  Spearman rho = {rho:.4f}, p (ketoldali) = {p_h2:.3e}")
    h2_pass = (rho > 0.30) and (p_h2 < 0.025)
    print(f"  C-H2 (rho>0.30 ES p<0.025): {'PASS' if h2_pass else 'FAIL'}")

    # ==================== Incremental R^2 ====================
    print()
    print("=" * 78)
    print("INCREMENTAL R^2 — confidence_score additiv magyarazo ereje")
    print("=" * 78)
    y = np.array([int(r["is_in_contradiction"]) for r in records], dtype=np.float64)
    cd_vals = np.array([r["chain_depth_score"] for r in records])
    si_vals = np.array([r["surprise_inverse_score"] for r in records])
    sh_vals = np.array([r["stuck_history_score"] for r in records])
    cdi_vals = np.array([r["contradiction_distance_score"] for r in records])
    conf_vals = np.array([r["confidence_score"] for r in records])
    n = len(records)
    bias = np.ones(n)
    # Modell A (baseline): bias + 4 nyers input
    X_A = np.column_stack([bias, cd_vals, si_vals, sh_vals, cdi_vals])
    # Modell B (full): A + confidence_score
    X_B = np.column_stack([bias, cd_vals, si_vals, sh_vals, cdi_vals, conf_vals])
    r2_A, _ = regress(X_A, y)
    r2_B, _ = regress(X_B, y)
    inc_r2 = r2_B - r2_A
    print(f"  R^2 (Modell A, 4 input): {r2_A:.4f}")
    print(f"  R^2 (Modell B, +confidence): {r2_B:.4f}")
    print(f"  Incremental R^2 = {inc_r2:.4f}")
    if inc_r2 > 0.05:
        ir_status = "PASS (nem-redundans)"
    elif inc_r2 >= 0.02:
        ir_status = "GRAY ZONE (reszleges nem-redundancia)"
    else:
        ir_status = "FAIL (redundans)"
    print(f"  Incremental R^2: {ir_status}")

    # ==================== VERDICT ====================
    print()
    print("=" * 78)
    print("VERDICT (pre-reg dontesfa szerint)")
    print("=" * 78)
    h1_p = h1_pass if (near and proven) else False
    h2_p = h2_pass
    if not v3_pass or not v4_pass:
        verdict = "INVALID_DUE_TO_PRECONDITION"
    elif inc_r2 < 0.02:
        verdict = "REDUNDANS — koncepcio cafolt"
    elif not h1_p:
        verdict = "near_contradiction NEM prediktiv — koncepcio cafolt"
    elif inc_r2 < 0.05:
        if h2_p:
            verdict = "RESZLEGES — H1+H2 PASS, de incremental R^2 gray zone"
        else:
            verdict = "RESZLEGES — H1 PASS, H2 FAIL, gray zone R^2"
    else:
        if h2_p:
            verdict = "MODUL C MEGEROSITVE — H1+H2 PASS, R^2 > 0.05"
        else:
            verdict = "RESZLEGES — H1 PASS, H2 FAIL"
    print(f"  {verdict}")


if __name__ == "__main__":
    main()
