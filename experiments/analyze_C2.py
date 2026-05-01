"""
Modul C v2 — formal pre-reg verdict-elemzés.

C2-H1 (elsődleges): rejekt-elt attempted élek confidence_score-ja < accepted-éké
        Mann-Whitney U, egyoldali, p < 0.025 (Bonferroni 2 teszt)

C2-H2 (elsődleges): multinomial logreg macro-F1 > class-prior baseline + 0.10
        p < 0.025 (Bonferroni 2 teszt)

C2-H3 (másodlagos): per-class precision a contradiction-on > prior + 0.20

Szürke zóna: macro-F1 lift ∈ [0.05, 0.10] → részleges nem-redundancia.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.mann_whitney import mann_whitney_u_greater


def softmax(z):
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def fit_multinomial_logreg(X, y, n_classes, n_iter=200, lr=0.1):
    """Egyszerű multinomial logreg gradient descent-tel."""
    n, k = X.shape
    W = np.zeros((k, n_classes))
    Y_onehot = np.eye(n_classes)[y.astype(int)]
    for _ in range(n_iter):
        z = X @ W
        p = softmax(z)
        grad = X.T @ (p - Y_onehot) / n
        W -= lr * grad
    return W


def predict(X, W):
    return softmax(X @ W).argmax(axis=1)


def macro_f1(y_true, y_pred, n_classes):
    f1s = []
    for c in range(n_classes):
        tp = ((y_true == c) & (y_pred == c)).sum()
        fp = ((y_true != c) & (y_pred == c)).sum()
        fn = ((y_true == c) & (y_pred != c)).sum()
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        if prec + rec > 0:
            f1s.append(2 * prec * rec / (prec + rec))
        else:
            f1s.append(0.0)
    return float(np.mean(f1s)), f1s


def per_class_precision(y_true, y_pred, c):
    tp = ((y_true == c) & (y_pred == c)).sum()
    fp = ((y_true != c) & (y_pred == c)).sum()
    return float(tp / max(tp + fp, 1))


def main():
    edge_path = ROOT / "experiments" / "runs" / "C2_formal" / "attempts.json"
    records = json.load(open(edge_path, encoding="utf-8"))
    print(f"Records: {len(records)}")

    # Outcome eloszlás
    counter = Counter(r["outcome"] for r in records)
    print(f"Outcome eloszlás: {dict(counter)}")

    # Csak a 3 érdekes osztály: accepted, contradiction, forbidden
    OUTCOMES = ["accepted", "contradiction", "forbidden"]
    filtered = [r for r in records if r["outcome"] in OUTCOMES]
    print(f"Filtered records (3 osztály): {len(filtered)}")
    counter_f = Counter(r["outcome"] for r in filtered)
    print(f"  {dict(counter_f)}")

    # Ha a forbidden ~ 0, használjunk csak 2 osztályt
    use_classes = [c for c in OUTCOMES if counter_f.get(c, 0) >= 10]
    print(f"Használt osztályok (>=10 minta): {use_classes}")
    if len(use_classes) < 2:
        print("FAIL: kevesebb mint 2 osztály — nem értékelhető")
        return

    # ==================== C2-H1 ====================
    print()
    print("=" * 78)
    print("C2-H1: rejekt-elt attempted élek confidence_score-ja < accepted-éké")
    print("=" * 78)
    accepted_conf = [r["confidence_score"] for r in filtered if r["outcome"] == "accepted"]
    rejected_conf = [r["confidence_score"] for r in filtered if r["outcome"] != "accepted"]
    print(f"  accepted: n={len(accepted_conf)}, median confidence={median(accepted_conf):.4f}")
    print(f"  rejected: n={len(rejected_conf)}, median confidence={median(rejected_conf):.4f}")
    if accepted_conf and rejected_conf:
        _, _, p_h1 = mann_whitney_u_greater(accepted_conf, rejected_conf)
        eff = median(accepted_conf) - median(rejected_conf)
        print(f"  Mann-Whitney p (egyoldali, accepted > rejected) = {p_h1:.3e}")
        print(f"  effektus: {eff:+.4f}")
        h1_pass = (p_h1 < 0.025) and (eff > 0)
        print(f"  C2-H1: {'PASS' if h1_pass else 'FAIL'}")
    else:
        h1_pass = False
        print("  C2-H1: nem értékelhető")

    # ==================== C2-H2 ====================
    print()
    print("=" * 78)
    print("C2-H2: multinomial logreg macro-F1 > class-prior baseline + 0.10")
    print("=" * 78)
    # Csak a használt osztályokra
    class_to_idx = {c: i for i, c in enumerate(use_classes)}
    keep = [r for r in filtered if r["outcome"] in class_to_idx]
    n_classes = len(use_classes)

    # Features: 4 input
    X_raw = np.array([
        [r["chain_depth_score"], r["surprise_inverse_score"],
         r["stuck_history_score"], r["contradiction_distance_score"]]
        for r in keep
    ])
    # Bias column
    X = np.column_stack([np.ones(len(keep)), X_raw])
    y = np.array([class_to_idx[r["outcome"]] for r in keep])

    # Train-test split (random 80-20)
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(keep))
    split = int(0.8 * len(keep))
    train_idx, test_idx = idx[:split], idx[split:]

    W = fit_multinomial_logreg(X[train_idx], y[train_idx], n_classes)
    y_pred_test = predict(X[test_idx], W)
    y_test = y[test_idx]

    f1, per_class = macro_f1(y_test, y_pred_test, n_classes)
    print(f"  Test set: n={len(y_test)}")
    print(f"  Macro-F1 (multinomial logreg): {f1:.4f}")
    for c, name in enumerate(use_classes):
        print(f"    {name}: F1={per_class[c]:.4f}")

    # Class-prior baseline: predict majority class
    majority_class = Counter(y[train_idx].tolist()).most_common(1)[0][0]
    y_pred_baseline = np.full_like(y_test, majority_class)
    f1_baseline, _ = macro_f1(y_test, y_pred_baseline, n_classes)
    print(f"  Class-prior macro-F1 (predict majority): {f1_baseline:.4f}")

    lift = f1 - f1_baseline
    print(f"  Macro-F1 lift: {lift:+.4f}")
    h2_pass = lift > 0.10
    if 0.05 <= lift <= 0.10:
        h2_status = "GRAY ZONE (részleges nem-redundancia)"
    elif lift > 0.10:
        h2_status = "PASS"
    else:
        h2_status = "FAIL"
    print(f"  C2-H2: {h2_status}")

    # ==================== C2-H3 ====================
    if "contradiction" in use_classes:
        print()
        print("=" * 78)
        print("C2-H3 (másodlagos): per-class precision a contradiction-on > prior + 0.20")
        print("=" * 78)
        c_idx = class_to_idx["contradiction"]
        prec_contra = per_class_precision(y_test, y_pred_test, c_idx)
        # Prior precision: ha véletlenszerűen jósolnánk contradiction-t (=class freq), hányszor lenne igaz?
        prior_prec = Counter(y_test.tolist()).get(c_idx, 0) / max(len(y_test), 1)
        lift3 = prec_contra - prior_prec
        print(f"  Contradiction class precision: {prec_contra:.4f}")
        print(f"  Prior precision (class freq): {prior_prec:.4f}")
        print(f"  Lift: {lift3:+.4f}")
        h3_pass = lift3 > 0.20
        print(f"  C2-H3: {'PASS' if h3_pass else 'FAIL'}")
    else:
        h3_pass = False

    # ==================== VERDICT ====================
    print()
    print("=" * 78)
    print("C2 VERDICT")
    print("=" * 78)
    if h1_pass and h2_status == "PASS":
        print("  MODUL C2 MEGEROSITVE — confidence_score prediktiv ÉS multinomial szignifikáns")
    elif h1_pass and h2_status == "GRAY ZONE":
        print("  RESZLEGES NEM-REDUNDANCIA — H1 PASS, multinomial gyenge (gray zone)")
    elif h1_pass:
        print("  RESZLEGES — confidence_score prediktiv (H1 PASS), de multinomial regr. nem szig.")
    elif h2_status == "PASS":
        print("  RESZLEGES — multinomial szig. (H2 PASS), de H1 FAIL")
    else:
        print("  CAFOLT — sem H1, sem H2 nem teljesül")


if __name__ == "__main__":
    main()
