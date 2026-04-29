"""
LinkedIn ábra: a két-mechanizmus kép vizualizációja.

Bal panel: TOPO eloszlások 4 karon — strukturáltság-jel (timeless > random),
            de az immunrendszer NEM befolyásolja (timeless ≈ no_immune ≈ random_immune).
Jobb panel: Q eloszlások — pont fordított mintázat: az immun CSÖKKENTI a Q-t.

Két szétválasztott, statisztikailag bizonyított mechanizmus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.aggregate import _parse_log


def final_values(manifest_path: Path, metric: str) -> list:
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    out = []
    for run in manifest["runs"]:
        parsed = _parse_log(Path(run["telemetry_log"]))
        if not parsed:
            continue
        last_tick = max(parsed.keys())
        out.append(parsed[last_tick][metric])
    return out


# Az A1 (48 csúcsos) strict karok — itt mind a strukturáltság, mind az immun hatás látszik
ARMS = [
    ("timeless_strict", "Tézis\n(struktúra +\nimmun)"),
    ("random_strict", "Random gráf\n(struktúra\nnélkül)"),
    ("no_immune_strict", "Struktúra,\nimmun nélkül"),
    ("random_immune_strict", "Struktúra,\nrandom immun"),
]

topo_data = []
q_data = []
labels = []
for arm_dir, label in ARMS:
    manifest = ROOT / "experiments" / "runs" / arm_dir / "manifest.json"
    topo_data.append(final_values(manifest, "topo"))
    q_data.append(final_values(manifest, "q"))
    labels.append(label)

# Színek: tézis (kiemelt), random (kontroll), két immun-kontroll
colors = ["#2E86AB", "#E63946", "#F4A261", "#F4A261"]

fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))
fig.patch.set_facecolor("white")

# ============ BAL PANEL: TOPO ============
ax = axes[0]
bp = ax.boxplot(
    topo_data, patch_artist=True, widths=0.6,
    medianprops=dict(color="black", linewidth=2),
    flierprops=dict(marker="o", markersize=4, alpha=0.5),
)
for patch, c in zip(bp["boxes"], colors):
    patch.set_facecolor(c)
    patch.set_alpha(0.75)
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylabel("Topológiai mélység (TOPO)", fontsize=12, fontweight="bold")
ax.set_title(
    "1. mechanizmus — STRUKTURÁLTSÁG hat a TOPO-ra\n"
    "(immunrendszernek nincs detektálható hatása)",
    fontsize=12, fontweight="bold", pad=12,
)
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(13, 29)

# Szignifikancia-jelzők — strukturáltság jel
ax.annotate(
    "p = 1.1 · 10⁻¹¹",
    xy=(1.5, 27.3), fontsize=12, ha="center",
    fontweight="bold", color="#2E86AB",
)
ax.plot([1, 2], [26.8, 26.8], "k-", linewidth=1.3)
ax.plot([1, 1], [26.3, 26.8], "k-", linewidth=1.3)
ax.plot([2, 2], [26.3, 26.8], "k-", linewidth=1.3)

# Immun-TOPO null-eredmény jelölés
ax.annotate(
    "n. sz.  (p > 0.2)",
    xy=(3.5, 27.3), fontsize=11, ha="center",
    color="#666", style="italic",
)
ax.plot([1, 4], [26.8, 26.8], "-", color="#888", linewidth=1.0, alpha=0.6)
ax.plot([3, 3], [26.3, 26.8], "-", color="#888", linewidth=1.0, alpha=0.6)
ax.plot([4, 4], [26.3, 26.8], "-", color="#888", linewidth=1.0, alpha=0.6)

# ============ JOBB PANEL: Q ============
ax = axes[1]
bp = ax.boxplot(
    q_data, patch_artist=True, widths=0.6,
    medianprops=dict(color="black", linewidth=2),
    flierprops=dict(marker="o", markersize=4, alpha=0.5),
)
for patch, c in zip(bp["boxes"], colors):
    patch.set_facecolor(c)
    patch.set_alpha(0.75)
ax.set_xticklabels(labels, fontsize=10)
ax.set_ylabel("Élsűrűség (Q)", fontsize=12, fontweight="bold")
ax.set_title(
    "2. mechanizmus — IMMUNRENDSZER hat a Q-ra\n"
    "(független a strukturáltság-mechanizmustól)",
    fontsize=12, fontweight="bold", pad=12,
)
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0.155, 0.215)

# Tézis vs no_immune
ax.annotate(
    "p = 1.2 · 10⁻¹¹   (~17%)",
    xy=(2, 0.211), fontsize=12, ha="center",
    fontweight="bold", color="#2E86AB",
)
ax.plot([1, 3], [0.207, 0.207], "k-", linewidth=1.3)
ax.plot([1, 1], [0.205, 0.207], "k-", linewidth=1.3)
ax.plot([3, 3], [0.205, 0.207], "k-", linewidth=1.3)

# Tézis vs random_immune (alacsonyabb szintű annotáció)
ax.annotate(
    "p = 1.4 · 10⁻¹¹",
    xy=(2.5, 0.198), fontsize=11, ha="center",
    fontweight="bold", color="#2E86AB",
)
ax.plot([1, 4], [0.194, 0.194], "k-", linewidth=1.3)
ax.plot([1, 1], [0.192, 0.194], "k-", linewidth=1.3)
ax.plot([4, 4], [0.192, 0.194], "k-", linewidth=1.3)

# ============ Általános cím ============
fig.suptitle(
    "Egy hipotézis két mechanizmussá vált — kontroll-kísérlet eredménye",
    fontsize=14, fontweight="bold", y=1.00,
)
fig.text(
    0.5, 0.012,
    "Axiomatikus következtető motor (AIE) — 30 független seed × 10000 lépés × 4 kar.  "
    "Mann-Whitney U, Bonferroni-korrekció.  Pre-regisztrált küszöbök.",
    ha="center", fontsize=9, style="italic", color="#444",
)

plt.tight_layout()
plt.subplots_adjust(top=0.88, bottom=0.12)

out = ROOT / "experiments" / "two_mechanism_result.png"
plt.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
print(f"Mentve: {out}")
