"""
Discovery napló sorainak átalakítása JSONL-be (hipotézis-napló, Fázis 3).

Formátum (discovery_log / discovery_log_relaxed.txt):
  timestamp pid=... Q=... edge i->j domain A->B
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, List, Optional

import edge_trust

LINE_RE = re.compile(
    r"^(?P<ts>[\d.]+)\s+pid=(?P<pid>\d+)\s+Q=(?P<q>[\d.]+)\s+"
    r"edge\s+(?P<i>\d+)->(?P<j>\d+)\s+domain\s+(?P<dom>.+)$"
)


def parse_discovery_lines(text: str) -> List[dict[str, Any]]:
    rows: List[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        rows.append(
            {
                "timestamp": float(m.group("ts")),
                "pid": int(m.group("pid")),
                "Q": float(m.group("q")),
                "edge_i": int(m.group("i")),
                "edge_j": int(m.group("j")),
                "domain": m.group("dom").strip(),
                "raw": line,
            }
        )
    return rows


def enrich_rows_with_trust(
    rows: List[dict[str, Any]], trust_path: Optional[Path]
) -> None:
    if not trust_path or not trust_path.is_file():
        for r in rows:
            r.setdefault("source_trust", 0.0)
        return
    tm = edge_trust.trust_map_from_store(trust_path)
    for r in rows:
        key = f"{r['edge_i']}->{r['edge_j']}"
        r["source_trust"] = tm.get(key, 0.0)


def sync_discovery_to_jsonl(
    discovery_path: Path,
    jsonl_path: Path,
    trust_path: Optional[Path] = None,
) -> int:
    """
    A discovery fájl teljes újraolvasása és JSONL írása.
    Vissza: beírt sorok száma.
    """
    if not discovery_path.is_file():
        return 0
    text = discovery_path.read_text(encoding="utf-8", errors="replace")
    rows = parse_discovery_lines(text)
    enrich_rows_with_trust(rows, trust_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Discovery log -> hypotheses JSONL")
    ap.add_argument(
        "--discovery",
        type=Path,
        default=Path("discovery_log_relaxed.txt"),
        help="Bemeneti discovery napló",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("hypotheses/discovered_edges.jsonl"),
        help="Kimeneti JSONL",
    )
    ap.add_argument(
        "--trust-store",
        type=Path,
        default=None,
        help="Opcionális: source_trust mező a JSONL sorokban (edge_trust.json)",
    )
    args = ap.parse_args()
    n = sync_discovery_to_jsonl(args.discovery, args.out, trust_path=args.trust_store)
    print(f"Írva: {n} sor -> {args.out}")


if __name__ == "__main__":
    main()
