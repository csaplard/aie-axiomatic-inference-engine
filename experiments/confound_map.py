"""
Confound-térkép — exploratórikus 2D paraméter-scan.

NEM pre-regisztrált hipotézis-teszt, hanem mérési-feltétel-feltérképezés:
hol a mátrixban (n_nodes × N_immune) tudunk egészséges méréseket csinálni?
A térkép azonosítja az "egészséges" (mérhető) és "confound-olt" (artefakt-domináns)
régiókat, mielőtt új pre-reg-elt kísérletet indítunk.

Cellánként 5 seed × 3000 lépés × strict-immune × uniform priority.
Output: CSV (mind a cellákra), heatmap PNG, és ASCII-tábla.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, median, stdev

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.aggregate import _parse_log
from experiments.registry_generators import (
    add_priority_to_dense,
    dense_synthetic_registry,
)


def _build_cell_registry(
    n: int, n_immune: int, out_dir: Path, adjacency_mode: str = "near"
) -> Path:
    """Egy (n, N) cellára: dense_synthetic + uniform priority + n_nodes_override."""
    base = dense_synthetic_registry(
        n_nodes=n,
        n_forbidden=n_immune,
        n_negation=n_immune,
        seed=1,
        adjacency_mode=adjacency_mode,
        n_nodes_override=n,
    )
    # uniform priority — confound-térkép nem priority-függő
    for node in base["nodes"]:
        node["priority_weight"] = 0.5
    out_path = out_dir / f"cell_n{n}_N{n_immune}_{adjacency_mode}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False)
    return out_path


def _run_seed(
    registry_path: Path, seed: int, n_steps: int, telemetry_path: Path
) -> dict:
    """Egy seed: engine indít, n_steps lépés, telemetria fájlba ír."""
    from axiom_kernel import AxiomaticInferenceEngine

    policy = {
        "discovery": {
            "enabled": True,
            "daemon_mode": True,
            "seed_hamilton_ring": False,  # NE legyen Hamilton-kör — torzítaná a TOPO-t
            "ignore_forbidden_edges": False,
            "ignore_negation_contradictions": False,
            "telemetry_enabled": True,
            "telemetry_log_path": str(telemetry_path),
            "log_path": str(telemetry_path) + ".disc",
            "telemetry_every_n_steps": 100,
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
        }
    }
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(policy, tf, allow_unicode=True)
    tf.close()
    policy_path = Path(tf.name)
    try:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True,
            policy_path=str(policy_path),
            registry_path=str(registry_path),
        )
        for _ in range(n_steps):
            eng.think_step()
        # Final values
        parsed = _parse_log(telemetry_path)
        if not parsed:
            return {"q": float("nan"), "topo": float("nan"), "rrr": float("nan")}
        last_tick = max(parsed.keys())
        last = parsed[last_tick]
        return {
            "q": last["q"],
            "topo": last["topo"],
            "rrr": last["rrr"],
        }
    finally:
        policy_path.unlink(missing_ok=True)


def _classify_cell(rrr_values: list, topo_values: list, n: int) -> str:
    """Cell-cimke heurisztikus szabályokkal."""
    rrr_med = median(rrr_values)
    rrr_std = stdev(rrr_values) if len(rrr_values) > 1 else 0.0
    topo_med = median(topo_values)
    topo_ratio = topo_med / n if n > 0 else 0

    if rrr_med > 0.95 and rrr_std < 0.05:
        return "RRR_saturated"  # immun saturáció
    if rrr_med < 0.02 and rrr_std < 0.02:
        return "RRR_silent"  # immun gyakorlatilag inaktív
    if topo_ratio > 0.95:
        return "TOPO_saturated"  # gráf telített
    return "healthy"


def run_cell(args: tuple) -> dict:
    """Egy cella futtatása: 5 seed × n_steps."""
    n, n_immune, registries_dir, runs_dir, n_seeds, n_steps, adjacency_mode = args
    reg = _build_cell_registry(n, n_immune, registries_dir, adjacency_mode)
    cell_runs_dir = runs_dir / f"n{n}_N{n_immune}_{adjacency_mode}"
    cell_runs_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for seed in range(n_seeds):
        tel = cell_runs_dir / f"seed_{seed:03d}.tel"
        r = _run_seed(reg, seed, n_steps, tel)
        results.append(r)

    rrrs = [r["rrr"] for r in results if r["rrr"] == r["rrr"]]  # NaN-szűrés
    topos = [r["topo"] for r in results if r["topo"] == r["topo"]]
    qs = [r["q"] for r in results if r["q"] == r["q"]]

    label = _classify_cell(rrrs, topos, n)
    return {
        "n": n,
        "N_immune": n_immune,
        "adjacency": adjacency_mode,
        "rrr_med": median(rrrs) if rrrs else float("nan"),
        "rrr_std": stdev(rrrs) if len(rrrs) > 1 else 0.0,
        "rrr_min": min(rrrs) if rrrs else float("nan"),
        "rrr_max": max(rrrs) if rrrs else float("nan"),
        "q_med": median(qs) if qs else float("nan"),
        "topo_med": median(topos) if topos else float("nan"),
        "topo_ratio": (median(topos) / n if topos and n > 0 else float("nan")),
        "label": label,
    }


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--adjacency", choices=["near", "far", "uniform"], default="near"
    )
    ap.add_argument("--n-seeds", type=int, default=5)
    ap.add_argument("--n-steps", type=int, default=3000)
    args = ap.parse_args()

    n_grid = [40, 60, 80, 100]
    N_grid = [1, 2, 3, 5]
    n_seeds = args.n_seeds
    n_steps = args.n_steps
    adjacency_mode = args.adjacency

    registries_dir = ROOT / "experiments" / "registries" / "_confound_map"
    registries_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = ROOT / "experiments" / "runs" / f"_confound_map_{adjacency_mode}"
    runs_dir.mkdir(parents=True, exist_ok=True)

    cells = [(n, N, registries_dir, runs_dir, n_seeds, n_steps, adjacency_mode)
             for n in n_grid for N in N_grid]

    print(f"Confound-térkép: {len(cells)} cella, {n_seeds} seed × {n_steps} lépés / cella")
    print(f"  adjacency: {adjacency_mode}")
    print(f"  n grid: {n_grid}")
    print(f"  N grid: {N_grid}")
    print()
    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run_cell, c): (c[0], c[1]) for c in cells}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print(f"  done: n={r['n']:2d} N={r['N_immune']:2d}  "
                  f"RRR={r['rrr_med']:.3f}±{r['rrr_std']:.3f}  "
                  f"Q={r['q_med']:.4f}  "
                  f"TOPO/n={r['topo_ratio']:.2f}  "
                  f"label={r['label']}", flush=True)
    elapsed = time.time() - t0
    print(f"\nÖssz idő: {elapsed:.0f} s")

    # Sorbarendezés (n, N) szerint
    results.sort(key=lambda r: (r["n"], r["N_immune"]))

    # CSV
    csv_path = runs_dir / f"confound_map_{adjacency_mode}.csv"
    fieldnames = list(results[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)
    print(f"CSV: {csv_path}")

    # ASCII tábla
    print()
    print("=" * 78)
    print("CONFOUND-MAP (oszlopok: N_immune, sorok: n_nodes)")
    print("=" * 78)
    print(f"  Cell formátum: RRR_med | TOPO/n | label")
    print()
    header = f"{'n \\ N':>6} | " + " | ".join(f"{N:>16d}" for N in N_grid)
    print(header)
    print("-" * len(header))
    for n in n_grid:
        cells_n = [r for r in results if r["n"] == n]
        cells_n.sort(key=lambda r: r["N_immune"])
        row = f"{n:>6d} | "
        cell_strs = []
        for r in cells_n:
            cell_strs.append(
                f"{r['rrr_med']:>4.2f}/{r['topo_ratio']:>4.2f} {r['label'][:8]:>8s}"
            )
        row += " | ".join(cell_strs)
        print(row)

    # Heatmap PNG (egyszerű matplotlib)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        rrr_grid = np.zeros((len(n_grid), len(N_grid)))
        topo_grid = np.zeros((len(n_grid), len(N_grid)))
        labels_grid = [[None] * len(N_grid) for _ in n_grid]
        for r in results:
            i = n_grid.index(r["n"])
            j = N_grid.index(r["N_immune"])
            rrr_grid[i, j] = r["rrr_med"]
            topo_grid[i, j] = r["topo_ratio"]
            labels_grid[i][j] = r["label"]

        fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
        for ax, grid, title, vmin, vmax in [
            (axes[0], rrr_grid, "RRR (immun-aktivitás)", 0.0, 1.0),
            (axes[1], topo_grid, "TOPO / n (TOPO-saturáció)", 0.0, 1.0),
        ]:
            im = ax.imshow(grid, cmap="RdYlGn_r", vmin=vmin, vmax=vmax, aspect="auto")
            ax.set_xticks(range(len(N_grid)))
            ax.set_xticklabels(N_grid)
            ax.set_yticks(range(len(n_grid)))
            ax.set_yticklabels(n_grid)
            ax.set_xlabel("N_immune (forbidden + negation pair)")
            ax.set_ylabel("n_nodes")
            ax.set_title(title)
            for i in range(len(n_grid)):
                for j in range(len(N_grid)):
                    ax.text(
                        j, i, f"{grid[i, j]:.2f}",
                        ha="center", va="center",
                        color="white" if grid[i, j] > 0.6 else "black",
                        fontsize=10,
                    )
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        fig.suptitle(
            "Confound-térkép — méréskondíciók a (n_nodes, N_immune) paraméter-térben",
            fontsize=13, fontweight="bold",
        )
        plt.tight_layout()
        png_path = runs_dir / f"confound_map_{adjacency_mode}.png"
        plt.savefig(png_path, dpi=150, bbox_inches="tight", facecolor="white")
        print(f"\nHeatmap: {png_path}")
    except Exception as e:
        print(f"  (heatmap kihagyva: {e})")


if __name__ == "__main__":
    main()
