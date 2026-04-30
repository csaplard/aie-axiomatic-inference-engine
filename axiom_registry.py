"""
Betölti az axióma-regisztert (JSON), kulcsszó → csúcs index leképezést és tiltott éleket épít.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def normalize_text(s: str) -> str:
    """Kisbetű + ékezetmentes egyezéshez (magyar kulcsszavak)."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass(frozen=True)
class AxiomSpec:
    id: str
    index: int
    domain: str
    formula: str
    keywords: Tuple[str, ...]
    variables: Tuple[str, ...]
    priority_weight: float = 0.5


class AxiomRegistry:
    """JSON-ból: csúcsok, kulcsszavak (leghosszabb egyezés előnyben), kauzális és tiltott élek."""

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.version: str = data.get("version", "")
        self.nodes: List[AxiomSpec] = []
        id_to_index: Dict[str, int] = {}
        for idx, raw in enumerate(data["nodes"]):
            pw = raw.get("priority_weight", 0.5)
            try:
                pw_f = float(pw)
            except (TypeError, ValueError):
                pw_f = 0.5
            pw_f = max(0.0, min(1.0, pw_f))
            spec = AxiomSpec(
                id=raw["id"],
                index=idx,
                domain=raw.get("domain", "UNKNOWN"),
                formula=raw.get("formula", ""),
                keywords=tuple(raw.get("keywords", [])),
                variables=tuple(raw.get("variables", [])),
                priority_weight=pw_f,
            )
            self.nodes.append(spec)
            id_to_index[spec.id] = idx

        self._id_to_index = id_to_index
        pairs: List[Tuple[str, int]] = []
        for spec in self.nodes:
            for kw in spec.keywords:
                kn = normalize_text(kw)
                if kn:
                    pairs.append((kn, spec.index))
        pairs.sort(key=lambda x: len(x[0]), reverse=True)
        self._keyword_pairs: List[Tuple[str, int]] = pairs

        self.causal_edges: List[Tuple[int, int]] = []
        for a, b in data.get("causal_edges", []):
            if a in id_to_index and b in id_to_index:
                self.causal_edges.append((id_to_index[a], id_to_index[b]))

        self.forbidden_edges: Set[Tuple[int, int]] = set()
        for a, b in data.get("forbidden_edges", []):
            if a in id_to_index and b in id_to_index:
                self.forbidden_edges.add((id_to_index[a], id_to_index[b]))

        self.logical_negation_pairs: List[Tuple[int, int]] = []
        for a, b in data.get("logical_negation_pairs", []):
            if a in id_to_index and b in id_to_index:
                self.logical_negation_pairs.append((id_to_index[a], id_to_index[b]))

    @property
    def n_axioms(self) -> int:
        return len(self.nodes)

    def priority_array(self) -> List[float]:
        """priority_weight ∈ [0,1] minden csúcsra (index szerint rendezve)."""
        return [s.priority_weight for s in self.nodes]

    def resolve_id(self, ax_id: str) -> Optional[int]:
        return self._id_to_index.get(ax_id)

    def match_keyword(self, text: str) -> Optional[int]:
        """Első leghosszabb kulcsszó egyezés a normalizált szövegben."""
        if not text.strip():
            return None
        norm = normalize_text(text)
        if not norm:
            return None
        for kw, idx in self._keyword_pairs:
            if kw in norm:
                return idx
        return None

    def get_spec(self, index: int) -> Optional[AxiomSpec]:
        if 0 <= index < len(self.nodes):
            return self.nodes[index]
        return None

    def get_axiom_by_index(self, index: int) -> Optional[AxiomSpec]:
        """Alias a get_spec-hez (API: registry.get_axiom_by_index(i))."""
        return self.get_spec(index)
