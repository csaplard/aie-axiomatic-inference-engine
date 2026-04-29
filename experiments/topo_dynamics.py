"""
TOPO növekedési ráta dinamika és N* operacionalizálás.

Operacionális N* definíció (post-hoc fittelés helyett DINAMIKAI küszöb):
N* = az a tick, amelynél a (per-seed) TOPO növekedési rátája dTOPO/dt
     az átlagos KEZDETI rátához képest egy adott küszöb (alap: 10%) alá esik.

Ez a "fázisátmenet az aktív gráfépítés és a telített topológia között".

A definíció a növekedés *dinamikájáról* szól (relatív az adott seed kezdeti
ütemére), nem egy abszolút TOPO-küszöbről, így nem post-hoc kalibráció.

Bemenet: experiments/runs/<arm>/manifest.json (egy vagy több)
Kimenet:
  - per-seed N* (None ha sosem esik a küszöb alá)
  - kar-szintű medián és IQR
  - összehasonlító táblázat
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

from experiments.aggregate import _parse_log


def _topo_series(log_path: Path) -> List[Tuple[int, float]]:
    """tick-rendezett (tick, topo) párok egy seed log-jából."""
    parsed = _parse_log(log_path)
    return sorted((t, parsed[t]["topo"]) for t in parsed)


def _growth_rates(series: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
    """Diszkrét dTOPO/dt: (tick, ráta) — a t és t-1 közti TOPO-különbség
    osztva a tick-távolsággal. Az első pontot kihagyjuk (nincs előző)."""
    out: List[Tuple[int, float]] = []
    for k in range(1, len(series)):
        t_prev, v_prev = series[k - 1]
        t_cur, v_cur = series[k]
        dt = t_cur - t_prev
        if dt <= 0:
            continue
        out.append((t_cur, (v_cur - v_prev) / dt))
    return out


def n_star_for_seed(
    log_path: Path,
    initial_window: int,
    rate_fraction: float,
    sustain: int,
) -> Optional[int]:
    """
    Egyetlen seed N*-ja:
      - kezdeti ráta r0 = az első `initial_window` mérési pont átlagos rátája
      - N* = legkorábbi tick, amelytől kezdve `sustain` egymást követő mérésen
        a ráta < rate_fraction * r0
      - None, ha sosem teljesül
    """
    series = _topo_series(log_path)
    rates = _growth_rates(series)
    if len(rates) < initial_window + sustain:
        return None
    initial = [r for _, r in rates[:initial_window]]
    r0 = sum(initial) / len(initial)
    if r0 <= 0:
        return None
    threshold = rate_fraction * r0
    for k in range(initial_window, len(rates) - sustain + 1):
        window_rates = [rates[k + j][1] for j in range(sustain)]
        if all(r < threshold for r in window_rates):
            return rates[k][0]
    return None


def analyze_arm(
    manifest_path: Path,
    initial_window: int,
    rate_fraction: float,
    sustain: int,
) -> Dict[str, object]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    per_seed: Dict[int, Optional[int]] = {}
    for run in manifest["runs"]:
        log = Path(run["telemetry_log"])
        per_seed[int(run["seed"])] = n_star_for_seed(
            log, initial_window, rate_fraction, sustain
        )

    found = [v for v in per_seed.values() if v is not None]
    n_total = len(per_seed)
    coverage = len(found) / n_total if n_total else 0.0

    if found:
        srt = sorted(found)
        med = median(srt)
        q1 = srt[len(srt) // 4]
        q3 = srt[(3 * len(srt)) // 4]
    else:
        med = q1 = q3 = float("nan")

    return {
        "arm": manifest["name"],
        "n_seeds": n_total,
        "n_found": len(found),
        "coverage": coverage,
        "n_star_median": med,
        "n_star_q1": q1,
        "n_star_q3": q3,
        "per_seed": per_seed,
    }


def _final_topo_per_seed(manifest_path: Path) -> List[float]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    out: List[float] = []
    for run in manifest["runs"]:
        series = _topo_series(Path(run["telemetry_log"]))
        if not series:
            continue
        out.append(series[-1][1])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="TOPO növekedési ráta + N* operacionalizálás."
    )
    ap.add_argument(
        "--manifest", type=Path, action="append", required=True,
        help="Egy vagy több manifest. Kar-név a manifest['name']-ből.",
    )
    ap.add_argument(
        "--initial-window", type=int, default=3,
        help="Hány mérési pont átlaga adja a kezdeti rátát (alap: 3 = ~300 lépés).",
    )
    ap.add_argument(
        "--rate-fraction", type=float, default=0.1,
        help="A kezdeti ráta hány-szorosa alá kell csökkennie (alap: 0.1 = 10%%).",
    )
    ap.add_argument(
        "--sustain", type=int, default=3,
        help="Ennyi egymás utáni mérésen kell tartania a küszöb alatt.",
    )
    ap.add_argument(
        "--out-json", type=Path, default=None,
        help="Opcionális JSON-kimenet az összegzéssel.",
    )
    args = ap.parse_args()

    print()
    print("=" * 78)
    print("TOPO NÖVEKEDÉSI RÁTA + N* DINAMIKAI DEFINÍCIÓ")
    print("=" * 78)
    print(
        f"  initial_window={args.initial_window}, "
        f"rate_fraction={args.rate_fraction}, sustain={args.sustain}"
    )
    print()

    arms_summary: List[Dict[str, object]] = []
    for m in args.manifest:
        s = analyze_arm(m, args.initial_window, args.rate_fraction, args.sustain)
        finals = _final_topo_per_seed(m)
        s["topo_final_median"] = median(finals) if finals else float("nan")
        s["_manifest_path"] = str(m)
        arms_summary.append(s)

    print(f"{'arm':<18} {'n_seeds':>8} {'cov':>6} {'N*_med':>10} {'N*_Q1':>10} {'N*_Q3':>10} {'TOPO_final_med':>16}")
    print("-" * 78)
    for s in arms_summary:
        n_star_med = s["n_star_median"]
        n_star_str = (
            "NaN" if (isinstance(n_star_med, float) and math.isnan(n_star_med))
            else f"{n_star_med}"
        )
        q1_str = (
            "NaN" if (isinstance(s["n_star_q1"], float) and math.isnan(s["n_star_q1"]))
            else f"{s['n_star_q1']}"
        )
        q3_str = (
            "NaN" if (isinstance(s["n_star_q3"], float) and math.isnan(s["n_star_q3"]))
            else f"{s['n_star_q3']}"
        )
        print(
            f"{str(s['arm']):<18} {s['n_seeds']:>8} {s['coverage']:>5.0%} "
            f"{n_star_str:>10} {q1_str:>10} {q3_str:>10} "
            f"{s['topo_final_median']:>16.1f}"
        )

    print()
    if args.out_json is not None:
        with args.out_json.open("w", encoding="utf-8") as f:
            json.dump(arms_summary, f, ensure_ascii=False, indent=2)
        print(f"JSON: {args.out_json}")


if __name__ == "__main__":
    main()
