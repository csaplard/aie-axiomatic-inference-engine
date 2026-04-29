"""
Újragenerálja az axioms_registry_timeless.json fájlt az axioms_registry.json-ból.

Kiszűrt csúcsok: entropy_2nd, boltzmann_entropy, time_arrow (időtlen kísérlet bázis).

Használat (a projekt gyökeréből):
  python tools/build_timeless_registry.py
  python tools/build_timeless_registry.py --source masik.json --output axioms_registry_timeless.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DROP_IDS = frozenset({"entropy_2nd", "boltzmann_entropy", "time_arrow"})


def build_timeless(data: dict) -> dict:
    nodes = [n for n in data["nodes"] if n["id"] not in DROP_IDS]
    ids = {n["id"] for n in nodes}

    def filt(pairs: list) -> list:
        out = []
        for item in pairs:
            if len(item) != 2:
                continue
            a, b = item[0], item[1]
            if a in ids and b in ids:
                out.append([a, b])
        return out

    ver = str(data.get("version", "1.0"))
    if not ver.endswith("-timeless"):
        ver_out = f"{ver}-timeless"
    else:
        ver_out = ver

    return {
        "version": ver_out,
        "description": (
            "Időtlen kísérlet: nincs II. főtétel / Boltzmann / time_arrow; "
            "generálva: tools/build_timeless_registry.py"
        ),
        "nodes": nodes,
        "logical_negation_pairs": filt(data.get("logical_negation_pairs", [])),
        "causal_edges": filt(data.get("causal_edges", [])),
        "forbidden_edges": filt(data.get("forbidden_edges", [])),
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Időtlen axióma-regiszter szűrése.")
    ap.add_argument(
        "--source",
        type=Path,
        default=root / "axioms_registry.json",
        help="Bemeneti teljes regiszter",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=root / "axioms_registry_timeless.json",
        help="Kimeneti fájl",
    )
    args = ap.parse_args()
    src = args.source.resolve()
    if not src.is_file():
        raise SystemExit(f"Nincs ilyen fájl: {src}")

    data = json.loads(src.read_text(encoding="utf-8"))
    out = build_timeless(data)
    dst = args.output.resolve()
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {dst}")
    print(f"  nodes: {len(out['nodes'])}  causal_edges: {len(out['causal_edges'])}  forbidden: {len(out['forbidden_edges'])}  negation_pairs: {len(out['logical_negation_pairs'])}")


if __name__ == "__main__":
    main()
