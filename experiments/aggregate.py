"""
Telemetria-aggregálás: seed-enkénti Q, ASYM, TOPO, RRR idősorok → tick-enkénti
átlag és 95% konfidencia-intervallum.

Bemenet: experiments/runs/<name>/manifest.json
Kimenet: experiments/runs/<name>/aggregate.csv és aggregate.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple

LINE_RE = re.compile(
    r"\[TICK:\s*(\d+)\].*?Q=([\d.]+).*?DIST\(MACRO->MICRO\)=(\S+).*?"
    r"B_EFFICIENCY=([\d.]+).*?TOPO=(\d+).*?RRR=([\d.]+).*?ASYM=([\d.]+)"
)


def _parse_log(path: Path) -> Dict[int, Dict[str, float]]:
    """tick → {q, dist, b, topo, rrr, asym}. inf dist NaN-ra konvertálva."""
    out: Dict[int, Dict[str, float]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = LINE_RE.search(line)
            if not m:
                continue
            tick = int(m.group(1))
            dist_raw = m.group(3)
            dist = float("nan") if dist_raw == "inf" else float(dist_raw)
            out[tick] = {
                "q": float(m.group(2)),
                "dist": dist,
                "b": float(m.group(4)),
                "topo": float(m.group(5)),
                "rrr": float(m.group(6)),
                "asym": float(m.group(7)),
            }
    return out


def _ci95(values: List[float]) -> Tuple[float, float, float]:
    """Visszaadja: (mean, lower, upper). NaN-eket kihagyja."""
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return (float("nan"), float("nan"), float("nan"))
    mu = mean(vals)
    if len(vals) < 2:
        return (mu, mu, mu)
    sd = stdev(vals)
    half = 1.96 * sd / math.sqrt(len(vals))
    return (mu, mu - half, mu + half)


def aggregate(manifest_path: Path) -> Dict[str, object]:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    per_seed: Dict[int, Dict[int, Dict[str, float]]] = {}
    for run in manifest["runs"]:
        log_path = Path(run["telemetry_log"])
        per_seed[int(run["seed"])] = _parse_log(log_path)

    all_ticks = sorted({t for series in per_seed.values() for t in series})
    metrics = ("q", "dist", "topo", "rrr", "asym")

    rows: List[Dict[str, object]] = []
    for tick in all_ticks:
        row: Dict[str, object] = {"tick": tick}
        for metric in metrics:
            vals = [
                per_seed[s][tick][metric]
                for s in per_seed
                if tick in per_seed[s]
            ]
            mu, lo, hi = _ci95(vals)
            row[f"{metric}_mean"] = mu
            row[f"{metric}_ci_lo"] = lo
            row[f"{metric}_ci_hi"] = hi
            row[f"{metric}_n"] = len(vals)
        rows.append(row)

    summary = {
        "manifest": str(manifest_path),
        "n_seeds": len(per_seed),
        "n_ticks": len(all_ticks),
        "rows": rows,
    }
    return summary


def write_csv(summary: Dict[str, object], out_path: Path) -> None:
    rows = summary["rows"]  # type: ignore[assignment]
    if not rows:
        out_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())  # type: ignore[index]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)  # type: ignore[arg-type]


def main() -> None:
    ap = argparse.ArgumentParser(description="Telemetria aggregálás (mean ± 95% CI).")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out-csv", type=Path, default=None)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    summary = aggregate(args.manifest)
    out_csv = args.out_csv or args.manifest.parent / "aggregate.csv"
    out_json = args.out_json or args.manifest.parent / "aggregate.json"
    write_csv(summary, out_csv)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"CSV: {out_csv}")
    print(f"JSON: {out_json}")
    print(f"Seeds: {summary['n_seeds']}, ticks: {summary['n_ticks']}")


if __name__ == "__main__":
    main()
