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
        # Opcionális: ha a regiszter explicit megadja az engine n_nodes méretét.
        # Ha None, a kernel a saját default-jával dolgozik (max(default, n_axioms)).
        nn = data.get("n_nodes_override")
        try:
            self.n_nodes_override: Optional[int] = int(nn) if nn is not None else None
        except (TypeError, ValueError):
            self.n_nodes_override = None
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

        # Domain-szintű negation_pairs: Cartesian expansion node-szintre.
        # Ha "negation_domain_pairs": [["LOGIC", "INFO"], ...] szerepel,
        # minden LOGIC csúcsot összepárosítunk minden INFO csúccsal.
        # Védelem a kombinatorikai robbanás ellen: max_per_domain_pair cap.
        self.negation_domain_pairs: List[Tuple[str, str]] = []
        domain_pairs_raw = data.get("negation_domain_pairs", [])
        max_per_pair = int(data.get("negation_domain_pairs_cap", 500))
        domain_to_indices: Dict[str, List[int]] = {}
        for spec in self.nodes:
            domain_to_indices.setdefault(spec.domain, []).append(spec.index)
        added_pairs: Set[Tuple[int, int]] = set(
            (a, b) for a, b in self.logical_negation_pairs
        )
        added_pairs |= {(b, a) for a, b in self.logical_negation_pairs}
        # Reprodukálhatóság: deterministic shuffle a registry-szintű seed alapján
        seed = int(data.get("negation_domain_pairs_seed", 42))
        import random as _py_random
        rng = _py_random.Random(seed)

        for da, db in domain_pairs_raw:
            self.negation_domain_pairs.append((str(da), str(db)))
            ia = list(domain_to_indices.get(str(da), []))
            ib = list(domain_to_indices.get(str(db), []))
            # Az ÖSSZES Cartesian pár listáját generáljuk, majd shuffle + cap
            all_pairs = [(u, v) for u in ia for v in ib if u != v]
            rng.shuffle(all_pairs)
            count = 0
            for u, v in all_pairs:
                pair = (u, v)
                if pair in added_pairs:
                    continue
                if count >= max_per_pair:
                    break
                self.logical_negation_pairs.append(pair)
                added_pairs.add(pair)
                added_pairs.add((v, u))
                count += 1

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
