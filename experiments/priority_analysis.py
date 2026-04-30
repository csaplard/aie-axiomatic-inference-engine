"""
C kísérlet — pre-regisztrált H1-H5 elemzés.
Mann-Whitney U statisztikák a TOPO_high vs TOPO_low, és a karok közti összevetésekre.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.aggregate import _parse_log
from experiments.mann_whitney import mann_whitney_u_greater


def final_per_seed(manifest_path: Path, metric: str) -> list:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    out = []
    for run in manifest["runs"]:
        parsed = _parse_log(Path(run["telemetry_log"]))
        if not parsed:
            continue
        last_tick = max(parsed.keys())
        v = parsed[last_tick].get(metric)
        if v is not None:
            out.append(float(v))
    return out


def report(name: str, a: list, b: list, direction: str = "greater") -> None:
    if direction == "greater":
        U, z, p = mann_whitney_u_greater(a, b)
    else:
        U, z, p = mann_whitney_u_greater(b, a)
    print(
        f"  {name:50s}  med_a={median(a):>6.2f}  med_b={median(b):>6.2f}  "
        f"U={U:>6.1f}  z={z:>+5.2f}  p={p:.3e}"
    )


def main() -> None:
    runs_dir = ROOT / "experiments" / "runs"
    arms = ["priority_thesis", "priority_uniform", "priority_random", "priority_inverted"]
    manifests = {a: runs_dir / a / "manifest.json" for a in arms}

    print("=" * 80)
    print("C KÍSÉRLET — PRE-REGISZTRÁLT ELEMZÉS")
    print("=" * 80)

    # Adatok seedenként
    data = {}
    for arm, m in manifests.items():
        data[arm] = {
            "topo": final_per_seed(m, "topo"),
            "topo_high": final_per_seed(m, "topo_high"),
            "topo_low": final_per_seed(m, "topo_low"),
            "topo_ratio": final_per_seed(m, "topo_ratio"),
            "q": final_per_seed(m, "q"),
            "rrr": final_per_seed(m, "rrr"),
        }

    # ----- H1: priority_thesis TOPO_high > TOPO_low? -----
    print()
    print("H1 — priority_thesis: TOPO_high > TOPO_low?")
    print(f"   Pre-reg: ratio>1.5 ÉS p<0.0125 (Bonferroni 4 teszt)")
    th = data["priority_thesis"]
    ratio_med = median(th["topo_ratio"])
    print(f"   Aktuális ratio (medián): {ratio_med:.3f}")
    report("topo_high vs topo_low (priority_thesis)", th["topo_high"], th["topo_low"])
    h1_pass = ratio_med > 1.5
    print(f"   H1 verdict: {'PASS' if h1_pass else 'FAIL (ratio < 1.5 küszöb)'}")

    # ----- H2: priority_thesis össz-TOPO ~= priority_uniform? -----
    print()
    print("H2 — priority_thesis össz-TOPO ~= priority_uniform?")
    print(f"   Pre-reg: p > 0.05 (nincs szignifikáns globális eltérés)")
    # Kétoldali teszt: a 'greater' p kétszeres adja a kétoldali p-t (nagyjából)
    from experiments.mann_whitney import mann_whitney_u_greater as mwu
    a, b = data["priority_thesis"]["topo"], data["priority_uniform"]["topo"]
    _, _, p_g = mwu(a, b)
    _, _, p_l = mwu(b, a)
    p_two = 2.0 * min(p_g, p_l)
    print(
        f"   medians: thesis={median(a):.2f}, uniform={median(b):.2f}, "
        f"p (kétoldali) ~= {p_two:.3e}"
    )
    h2_pass = p_two > 0.05
    print(f"   H2 verdict: {'PASS (nincs szignifikáns eltérés)' if h2_pass else 'FAIL (van eltérés)'}")

    # ----- H3: priority_thesis Q ~= priority_uniform Q? -----
    print()
    print("H3 — priority_thesis Q ~= priority_uniform Q?")
    a, b = data["priority_thesis"]["q"], data["priority_uniform"]["q"]
    _, _, p_g = mwu(a, b)
    _, _, p_l = mwu(b, a)
    p_two = 2.0 * min(p_g, p_l)
    print(
        f"   medians: thesis={median(a):.4f}, uniform={median(b):.4f}, "
        f"p (kétoldali) ~= {p_two:.3e}"
    )
    h3_pass = p_two > 0.05
    print(f"   H3 verdict: {'PASS' if h3_pass else 'FAIL (Q szignifikánsan eltér)'}")

    # ----- H4: priority_thesis ratio vs priority_inverted ratio -----
    print()
    print("H4 — priority_thesis ratio vs priority_inverted ratio (irány-teszt)")
    print(f"   Pre-reg: thesis ratio > inverted ratio, p < 0.0125")
    a, b = data["priority_thesis"]["topo_ratio"], data["priority_inverted"]["topo_ratio"]
    inv_med = median(b)
    print(f"   medians: thesis_ratio={median(a):.3f}, inverted_ratio={inv_med:.3f}")
    report("thesis_ratio > inverted_ratio", a, b)
    # Pre-reg: inverted ratio < 0.7
    h4_inverted_low_enough = inv_med < 0.7
    print(f"   inverted ratio < 0.7 (pre-reg): {'PASS' if h4_inverted_low_enough else 'FAIL'}")

    # ----- H5: priority_random ratio ~= 1.0 -----
    print()
    print("H5 — priority_random ratio ~= 1.0?")
    a = data["priority_random"]["topo_ratio"]
    rand_med = median(a)
    print(f"   medián priority_random ratio: {rand_med:.3f} (pre-reg: ~1.0)")
    h5_pass = abs(rand_med - 1.0) < 0.2  # heurisztika
    print(f"   H5 verdict: {'PASS' if h5_pass else 'FAIL (jelentős eltérés 1.0-tól)'}")

    # ----- Globális összegzés -----
    print()
    print("=" * 80)
    print("VÉGEREDMÉNY — pre-regisztrált döntésfa")
    print("=" * 80)
    if h1_pass and h4_inverted_low_enough and h5_pass:
        print("  TÉZIS MEGERŐSÍTVE — priority koncentrál, irány-szenzitív, struktúra-függő")
    elif not h1_pass:
        print("  TÉZIS CÁFOLT — priority NEM koncentrálja a TOPO-t (ratio < 1.5)")
    else:
        print("  VEGYES — egyes hipotézisek átmentek, mások nem; részletes elemzés szükséges")

    # Adatok JSON-ba mentése
    out_path = ROOT / "experiments" / "runs" / "priority_analysis_summary.json"
    summary = {arm: {k: v for k, v in d.items()} for arm, d in data.items()}
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nRészletes adatok: {out_path}")


if __name__ == "__main__":
    main()
