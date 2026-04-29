#!/usr/bin/env python3
"""
AIE telemetria-sorokból (Q idősor) egyszerűsített Fisher-stílusú metrika és N-sweep.

A `axiom_kernel._maybe_telemetry_log` formátuma:
  PID=... [TICK: n] Q=0.xxxx | DIST(...)=... | ...

Ez a szkript **nem** a teljes Grammar Fingerprinting archívum másolata; ugyanarra a
célra (adathossz vs. információ) ad becslést: csúszóablakos minták kovarianciája,
precízió-mátrix trace (Fisher-hez hasonló skálázás). A becsült N* heurisztika.

Példa:
  python tools/telemetry_fisher_sweep.py --log telemetry_relaxed.log --out fisher_out.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Q_RE = re.compile(r"Q=([\d.eE+-]+)")


def parse_q_series(log_path: Path) -> np.ndarray:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    vals: list[float] = []
    for line in text.splitlines():
        m = Q_RE.search(line)
        if m:
            try:
                vals.append(float(m.group(1)))
            except ValueError:
                continue
    return np.array(vals, dtype=np.float64)


def sliding_window_matrix(q: np.ndarray, n: int, win: int) -> np.ndarray | None:
    """Első n Q érték; ablakméret win; soronként egy ablak."""
    seg = q[:n]
    if len(seg) < win + 2:
        return None
    rows = []
    for i in range(len(seg) - win):
        rows.append(seg[i : i + win])
    return np.array(rows, dtype=np.float64)


def fisher_trace_from_windows(X: np.ndarray, ridge: float = 1e-6) -> float:
    """Kovariancia precíziójának trace (Fisher-hez közeli skála, 1D ablakok)."""
    if X.shape[0] < X.shape[1] + 1:
        return float("nan")
    c = np.cov(X, rowvar=False)
    d = c.shape[0]
    c = c + ridge * np.eye(d)
    try:
        inv = np.linalg.inv(c)
    except np.linalg.LinAlgError:
        inv = np.linalg.pinv(c)
    return float(np.trace(inv))


def default_sweep_points(max_n: int) -> list[int]:
    base = [
        500,
        1000,
        2000,
        3000,
        4000,
        5000,
        6000,
        7000,
        8000,
        9000,
        10000,
        15000,
        20000,
        25000,
        30000,
    ]
    out = [p for p in base if p <= max_n]
    if max_n > 0 and (not out or out[-1] != max_n):
        if max_n not in out:
            out.append(max_n)
    return sorted(set(out))


def estimate_n_star(n_list: list[int], traces: list[float]) -> float | None:
    """|d(trace)/dN| maximumának közelítése (közbülső N)."""
    if len(n_list) < 3:
        return None
    ns = np.array(n_list, dtype=np.float64)
    ts = np.array(traces, dtype=np.float64)
    if np.any(~np.isfinite(ts)):
        return None
    d1 = np.diff(ts) / np.diff(ns)
    if d1.size == 0:
        return None
    idx = int(np.argmax(np.abs(d1)))
    return float((ns[idx] + ns[idx + 1]) / 2.0)


def run_sweep(
    q: np.ndarray,
    n_points: list[int],
    *,
    ridge: float,
) -> list[dict[str, float | int | str]]:
    max_n = len(q)
    rows: list[dict[str, float | int | str]] = []
    for n in n_points:
        if n > max_n:
            continue
        win = max(5, min(50, n // 100))
        X = sliding_window_matrix(q, n, win)
        if X is None:
            ft = float("nan")
        else:
            ft = fisher_trace_from_windows(X, ridge=ridge)
        rows.append(
            {
                "n_points": n,
                "window": win,
                "fisher_trace": ft,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Telemetria Q → Fisher-sweep (AIE)")
    ap.add_argument("--log", type=Path, required=True, help="Telemetria fájl")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Opcionális CSV kimenet",
    )
    ap.add_argument(
        "--ridge",
        type=float,
        default=1e-6,
        help="Ridge a kovarianciához",
    )
    args = ap.parse_args()

    if not args.log.is_file():
        raise SystemExit(f"Nincs fájl: {args.log}")

    q = parse_q_series(args.log)
    if q.size < 10:
        raise SystemExit(f"Túl kevés Q minta: {q.size}")

    n_points = default_sweep_points(int(q.size))
    rows = run_sweep(q, n_points, ridge=args.ridge)
    pairs = [
        (int(r["n_points"]), float(r["fisher_trace"]))
        for r in rows
        if math.isfinite(float(r["fisher_trace"]))
    ]
    n_star = (
        estimate_n_star([p[0] for p in pairs], [p[1] for p in pairs])
        if len(pairs) >= 3
        else None
    )

    print(f"Log: {args.log.resolve()}")
    print(f"Q minták száma: {q.size}")
    if n_star is not None:
        print(f"Becsült N* (|d(fisher_trace)/dN| max helye ~): ~{n_star:.0f}")
    else:
        print("N* becslés: nem adható (kevés pont).")
    print("---")

    fieldnames = ["source_log", "metric", "n_points", "window", "fisher_trace"]
    w = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    name = args.log.name
    for r in rows:
        w.writerow(
            {
                "source_log": name,
                "metric": "q",
                "n_points": r["n_points"],
                "window": r["window"],
                "fisher_trace": r["fisher_trace"],
            }
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as f:
            ww = csv.DictWriter(f, fieldnames=fieldnames)
            ww.writeheader()
            for r in rows:
                ww.writerow(
                    {
                        "source_log": name,
                        "metric": "q",
                        "n_points": r["n_points"],
                        "window": r["window"],
                        "fisher_trace": r["fisher_trace"],
                    }
                )
        print(f"CSV: {args.out.resolve()}", file=sys.stderr)


if __name__ == "__main__":
    main()
