"""
Per-él source_trust (Fázis 5): fájlban tárolt [-1, 1] skálás visszajelzés.

A discovery napló utolsó sora alapján a csevegő /jó és /rossz parancsai frissítik
a trust értéket; a daemon _discovery_log_edge ezt figyelembe veheti (policy).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LINE_RE = re.compile(
    r"^[\d.]+\s+pid=\d+\s+Q=[\d.]+\s+edge\s+(\d+)->(\d+)\s+domain\s+.+$"
)


def edge_key(i: int, j: int) -> str:
    return f"{int(i)}->{int(j)}"


def parse_last_discovery_edge(discovery_path: Path) -> tuple[int, int] | None:
    """Utolsó érvényes discovery sor: (i, j) indexek, vagy None."""
    if not discovery_path.is_file():
        return None
    try:
        lines = discovery_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def default_store() -> dict[str, Any]:
    return {"version": "1.0", "edges": {}}


def load_trust_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return default_store()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return default_store()
    if not isinstance(data, dict):
        return default_store()
    edges = data.get("edges")
    if not isinstance(edges, dict):
        data["edges"] = {}
    else:
        # normalizálás: str kulcs, float érték
        clean: dict[str, float] = {}
        for k, v in edges.items():
            try:
                clean[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        data["edges"] = clean
    data.setdefault("version", "1.0")
    return data


def save_trust_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_edge_trust(data: dict[str, Any], i: int, j: int) -> float:
    e = data.get("edges") or {}
    if not isinstance(e, dict):
        return 0.0
    v = e.get(edge_key(i, j))
    if v is None:
        return 0.0
    try:
        return max(-1.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def set_edge_trust(
    data: dict[str, Any], i: int, j: int, value: float, *, clamp: bool = True
) -> float:
    if "edges" not in data or not isinstance(data["edges"], dict):
        data["edges"] = {}
    v = float(value)
    if clamp:
        v = max(-1.0, min(1.0, v))
    data["edges"][edge_key(i, j)] = v
    return v


def bump_edge_trust(
    path: Path, i: int, j: int, delta: float, *, clamp: bool = True
) -> float:
    """delta hozzáadása; vissza: új trust."""
    data = load_trust_store(path)
    cur = get_edge_trust(data, i, j)
    new = cur + delta
    if clamp:
        new = max(-1.0, min(1.0, new))
    set_edge_trust(data, i, j, new, clamp=False)
    save_trust_store(path, data)
    return new


def trust_map_from_store(path: Path) -> dict[str, float]:
    """Gyors kulcs -> trust (üres fájl esetén {})."""
    data = load_trust_store(path)
    e = data.get("edges")
    if not isinstance(e, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in e.items():
        try:
            out[str(k)] = max(-1.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
    return out
