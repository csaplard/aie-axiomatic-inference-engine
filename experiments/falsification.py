"""
Falszifikációs assertion az AIE-tézisre.

Tézis (THEORY.md): a topológiai sorrend + immunrendszer együtt emergens "időnyíl"-
metaforát hoz létre — irányított, aszimmetrikus, mélyülő struktúrát.

Operacionalizált feltételek (alapérték — felülírható --criteria YAML-lal):

  - timeless: a K-edik tickre az ASYM mediánja (seed-eken át) >= 0.7,
              és a TOPO mediánja >= 5.
  - random:   a K-edik tickre az ASYM mediánja < 0.5
              (random gráfon ne legyen aszimmetria-jel).
  - symmetric: a K-edik tickre az ASYM mediánja < 0.5
              (szimmetrikus immunrendszerrel se legyen).

Ha a timeless megfelel, és a két kontroll alatta marad, a tézis NEM cáfolt.
Ha a kontrollok is elérik a küszöböt, a tézis CÁFOLT (a jel artefaktum).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional

import yaml


DEFAULT_CRITERIA: Dict[str, Dict[str, float]] = {
    "timeless": {"at_tick": 10000, "asym_min": 0.7, "topo_min": 5.0},
    "random": {"at_tick": 10000, "asym_max": 0.5},
    "symmetric": {"at_tick": 10000, "asym_max": 0.5},
}


def _row_at_tick(rows: List[Dict[str, float]], tick: int) -> Optional[Dict[str, float]]:
    """Legközelebbi tick-sor a megadott küszöbre (legalább X)."""
    candidates = [r for r in rows if int(r["tick"]) >= tick]
    if not candidates:
        return None
    return min(candidates, key=lambda r: int(r["tick"]))


def _seed_values_at_tick(
    manifest: Dict, metric: str, tick: int
) -> List[float]:
    """Seed-enkénti értékek a metrikához az adott tickre, mediánhoz."""
    from experiments.aggregate import _parse_log  # type: ignore

    out: List[float] = []
    for run in manifest["runs"]:
        log = _parse_log(Path(run["telemetry_log"]))
        ticks = sorted(log.keys())
        valid = [t for t in ticks if t >= tick]
        if not valid:
            continue
        chosen = valid[0]
        v = log[chosen][metric]
        if not math.isnan(v):
            out.append(v)
    return out


def check_arm(
    manifest_path: Path, arm: str, criteria: Dict[str, float]
) -> Dict[str, object]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    tick = int(criteria["at_tick"])
    asym_vals = _seed_values_at_tick(manifest, "asym", tick)
    topo_vals = _seed_values_at_tick(manifest, "topo", tick)
    asym_med = median(asym_vals) if asym_vals else float("nan")
    topo_med = median(topo_vals) if topo_vals else float("nan")

    result: Dict[str, object] = {
        "arm": arm,
        "manifest": str(manifest_path),
        "at_tick": tick,
        "n_seeds": len(asym_vals),
        "asym_median": asym_med,
        "topo_median": topo_med,
    }
    passed = True
    notes: List[str] = []
    if "asym_min" in criteria:
        ok = (not math.isnan(asym_med)) and asym_med >= criteria["asym_min"]
        passed = passed and ok
        notes.append(
            f"asym_median ({asym_med:.3f}) >= {criteria['asym_min']}: {'OK' if ok else 'FAIL'}"
        )
    if "asym_max" in criteria:
        ok = (not math.isnan(asym_med)) and asym_med <= criteria["asym_max"]
        passed = passed and ok
        notes.append(
            f"asym_median ({asym_med:.3f}) <= {criteria['asym_max']}: {'OK' if ok else 'FAIL'}"
        )
    if "topo_min" in criteria:
        ok = (not math.isnan(topo_med)) and topo_med >= criteria["topo_min"]
        passed = passed and ok
        notes.append(
            f"topo_median ({topo_med:.1f}) >= {criteria['topo_min']}: {'OK' if ok else 'FAIL'}"
        )
    result["passed"] = passed
    result["notes"] = notes
    return result


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Falszifikációs ellenőrzés timeless + random + symmetric karokra."
    )
    ap.add_argument("--timeless-manifest", type=Path, required=True)
    ap.add_argument("--random-manifest", type=Path, default=None)
    ap.add_argument("--symmetric-manifest", type=Path, default=None)
    ap.add_argument(
        "--criteria",
        type=Path,
        default=None,
        help="Opcionális YAML felülírja a DEFAULT_CRITERIA-t.",
    )
    args = ap.parse_args()

    crit = dict(DEFAULT_CRITERIA)
    if args.criteria is not None:
        with args.criteria.open(encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        for k, v in override.items():
            crit[k] = {**crit.get(k, {}), **v}

    arms: List[Dict[str, object]] = []
    arms.append(check_arm(args.timeless_manifest, "timeless", crit["timeless"]))
    if args.random_manifest is not None:
        arms.append(check_arm(args.random_manifest, "random", crit["random"]))
    if args.symmetric_manifest is not None:
        arms.append(
            check_arm(args.symmetric_manifest, "symmetric", crit["symmetric"])
        )

    print()
    print("=" * 60)
    print("FALSZIFIKÁCIÓS JELENTÉS")
    print("=" * 60)
    for a in arms:
        marker = "PASS" if a["passed"] else "FAIL"
        print(f"\n[{marker}] {a['arm']}  (n_seeds={a['n_seeds']}, tick>={a['at_tick']})")
        for n in a["notes"]:  # type: ignore[union-attr]
            print(f"   - {n}")

    timeless_ok = arms[0]["passed"]
    controls_ok = all(a["passed"] for a in arms[1:]) if len(arms) > 1 else None

    print("\n" + "-" * 60)
    if controls_ok is None:
        print("VÉGEREDMÉNY: nincs kontroll-kar — a tézis nem cáfolható egyedül.")
    elif timeless_ok and controls_ok:
        print("VÉGEREDMÉNY: a tézis NEM cáfolt (timeless aktív, kontrollok némák).")
    elif timeless_ok and not controls_ok:
        print(
            "VÉGEREDMÉNY: ARTEFAKTUM — a kontrollokon is megjelenik a jel,"
            " a tézis CÁFOLT."
        )
    else:
        print("VÉGEREDMÉNY: a timeless kar nem éri el a küszöböt — tézis NEM bizonyított.")
    print("-" * 60)


if __name__ == "__main__":
    main()
