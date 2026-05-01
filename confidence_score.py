"""
Modul C — ACC-analóg konfliktus-érzékelő: confidence_score(edge).

Négy input-jel min-aggregálva → confidence_score ∈ [0, 1].

A 4 input:
  1. chain_depth_score   — független transzitív bizonyító utak száma (cap-alapú)
  2. surprise_inverse    — DINAMIKUS: pár-ritkaság az utolsó N step ablakában (Laplace)
  3. stuck_history_score — Modul D detector eseményei, FOLYTONOS exp-csillapítással
  4. contradiction_dist  — LOGIKAI: shortest path j → neg(j) hossza

Episztemikus címkék (proven / hypothesis / uncertain / near_contradiction)
kvantilis-alapúak, a baseline daemon eloszlására kalibrálva.

A modul **stateless függvények** + egy `ConfidenceComputer` osztály a recent_window
karbantartásához. Az engine egy ConfidenceComputer-t használ (egyetlen instance
seedenként), a per-edge tagging-et a `compute()` metódus végzi.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np


# Default paraméterek (calibration override-olja)
DEFAULT_CHAIN_DEPTH_CAP = 5
DEFAULT_RECENT_WINDOW = 1000
DEFAULT_LAPLACE_K = 100  # P() denominator additivuma
DEFAULT_SURPRISE_NORM = 6.0  # -log(P) max-érték proxy (ha P~0.001, log≈6.9)
DEFAULT_STUCK_DECAY = 0.005  # exp(-0.005*age); half-life ~140 step
DEFAULT_STUCK_NORM = 5.0
DEFAULT_DIST_NORM = 20.0


def _shortest_path_length_excluding_edge(
    A: np.ndarray, src: int, dst: int, exclude_i: int, exclude_j: int
) -> float:
    """BFS shortest path src→dst, kivéve az (exclude_i, exclude_j) él használatát.
    Visszaadja: lépésszám, vagy float('inf') ha nincs út."""
    n = A.shape[0]
    if src == dst:
        return 0.0
    visited = [False] * n
    visited[src] = True
    q: Deque[Tuple[int, int]] = deque()
    q.append((src, 0))
    while q:
        u, d = q.popleft()
        # Successors: A[u, v] > 0
        for v in np.where(A[u, :] > 0)[0]:
            v = int(v)
            if visited[v]:
                continue
            # Az (exclude_i → exclude_j) élet kerüljük el
            if u == exclude_i and v == exclude_j:
                continue
            if v == dst:
                return float(d + 1)
            visited[v] = True
            q.append((v, d + 1))
    return float("inf")


class ConfidenceComputer:
    """Per-engine confidence_score számoló — recent_window pair-history fenntartása."""

    def __init__(
        self,
        chain_depth_cap: int = DEFAULT_CHAIN_DEPTH_CAP,
        recent_window: int = DEFAULT_RECENT_WINDOW,
        laplace_k: int = DEFAULT_LAPLACE_K,
        surprise_norm: float = DEFAULT_SURPRISE_NORM,
        stuck_decay: float = DEFAULT_STUCK_DECAY,
        stuck_norm: float = DEFAULT_STUCK_NORM,
        dist_norm: float = DEFAULT_DIST_NORM,
        granularity: str = "pair",
    ) -> None:
        self.chain_depth_cap = int(chain_depth_cap)
        self.recent_window = int(recent_window)
        self.laplace_k = int(laplace_k)
        self.surprise_norm = float(surprise_norm)
        self.stuck_decay = float(stuck_decay)
        self.stuck_norm = float(stuck_norm)
        self.dist_norm = float(dist_norm)
        self.granularity = granularity

        # Recent pair history (i, j) deque
        self._recent_pairs: Deque[Tuple[int, int]] = deque(maxlen=self.recent_window)
        self._recent_counts: Counter = Counter()
        # Stuck event history: list of (step_id, fired_key)
        self._stuck_events: List[Tuple[int, Tuple]] = []

    # ----------------------------------------- recent_window karbantartás
    def observe_pair(self, i: Optional[int], j: Optional[int]) -> None:
        """Minden think_step után meghívandó (idle is OK; akkor None, None)."""
        if i is None or j is None:
            return
        key = (int(i), int(j))
        # Eldobott elemet kivonjuk a counter-ből
        if len(self._recent_pairs) == self.recent_window:
            old = self._recent_pairs[0]
            self._recent_counts[old] -= 1
            if self._recent_counts[old] <= 0:
                del self._recent_counts[old]
        self._recent_pairs.append(key)
        self._recent_counts[key] += 1

    def observe_stuck_event(self, step_id: int, fired_key: Tuple) -> None:
        """A Modul D detector tüzelése után meghívható; a stuck-history-hoz."""
        self._stuck_events.append((int(step_id), fired_key))

    # ----------------------------------------- 4 input-jel számítása
    def chain_depth_score(self, A: np.ndarray, i: int, j: int) -> Tuple[float, int]:
        """Független transzitív utak száma (cap-alapú normalizálás)."""
        # k != i, j; A[i,k] > 0; A[k,j] > 0
        n = A.shape[0]
        n_paths = 0
        for k in range(n):
            if k == i or k == j:
                continue
            if A[i, k] > 0 and A[k, j] > 0:
                n_paths += 1
                if n_paths >= self.chain_depth_cap:
                    break
        score = min(n_paths, self.chain_depth_cap) / self.chain_depth_cap
        return float(score), int(n_paths)

    def surprise_inverse_score(
        self, i: int, j: int, axiom_labels: Optional[Dict[int, Any]] = None,
    ) -> Tuple[float, float]:
        """DINAMIKUS: az (i, j) pár ritkasága az utolsó recent_window step-ben.
        Visszaadja: (score, surprise_raw)."""
        if self.granularity == "domain" and axiom_labels is not None:
            # Domain-pár ritkaság (alternatív granularitás)
            di = axiom_labels.get(i)
            dj = axiom_labels.get(j)
            key = (
                str(di.value) if hasattr(di, "value") else str(di),
                str(dj.value) if hasattr(dj, "value") else str(dj),
            )
            count = sum(
                1 for (pi, pj) in self._recent_pairs
                if (
                    str(axiom_labels.get(pi, "X").value if hasattr(axiom_labels.get(pi), "value")
                        else axiom_labels.get(pi, "X")) == key[0]
                    and str(axiom_labels.get(pj, "X").value if hasattr(axiom_labels.get(pj), "value")
                            else axiom_labels.get(pj, "X")) == key[1]
                )
            )
        else:
            count = self._recent_counts.get((int(i), int(j)), 0)

        total = len(self._recent_pairs)
        # P(this pair) Laplace-simítva
        p = (count + 1) / (total + self.laplace_k)
        surprise_raw = -math.log(p)
        # exp(-surprise_raw / SURPRISE_NORM): magas surprise → alacsony score
        score = math.exp(-surprise_raw / self.surprise_norm)
        return float(min(max(score, 0.0), 1.0)), float(surprise_raw)

    def stuck_history_score(
        self, current_step: int, i: int, j: int,
        axiom_labels: Optional[Dict[int, Any]] = None,
    ) -> Tuple[float, float]:
        """FOLYTONOS exp-csillapítás a stuck eseményeken.
        Csak azokat veszi figyelembe, amelyek key-je megegyezik az (i,j)-vel
        (vagy domain-szinten illeszkedik)."""
        # Megkeressük a saját kulcsra eső stuck eseményeket
        if self.granularity == "domain" and axiom_labels is not None:
            di = axiom_labels.get(i)
            dj = axiom_labels.get(j)
            target = (
                str(di.value) if hasattr(di, "value") else str(di),
                str(dj.value) if hasattr(dj, "value") else str(dj),
            )
        else:
            target = (int(i), int(j))

        score_raw = 0.0
        for step_id, fired_key in self._stuck_events:
            if fired_key == target:
                age = max(0, current_step - step_id)
                score_raw += math.exp(-self.stuck_decay * age)

        normalized = min(score_raw / self.stuck_norm, 1.0)
        score = max(0.0, 1.0 - normalized)
        return float(score), float(score_raw)

    def contradiction_distance_score(
        self, A: np.ndarray, i: int, j: int,
        negation_map: Dict[int, Any],
    ) -> Tuple[float, float]:
        """LOGIKAI: shortest path j → ANY neg(j), kivéve az (i, j) él használatát.

        Visszafelé-kompatibilis: a negation_map értéke lehet egyetlen int
        (régi API) vagy List[int] (új API, több negation-jelölt).
        A score a legrövidebb távolságot számolja MINDEN candidate-ra.
        """
        candidates_raw = negation_map.get(int(j))
        if candidates_raw is None:
            return 1.0, float("inf")
        # Listává normalizáljuk
        if isinstance(candidates_raw, int):
            candidates = [int(candidates_raw)]
        else:
            candidates = [int(x) for x in candidates_raw]
        if not candidates:
            return 1.0, float("inf")
        # Minden candidate-ra: shortest path j → neg, és vegyük a minimumot
        min_d = float("inf")
        for nj in candidates:
            d = _shortest_path_length_excluding_edge(A, int(j), nj, int(i), int(j))
            if d < min_d:
                min_d = d
        if math.isinf(min_d):
            return 1.0, min_d
        score = min(min_d / self.dist_norm, 1.0)
        return float(score), float(min_d)

    # ----------------------------------------- aggregáció
    def compute(
        self,
        A: np.ndarray,
        i: int,
        j: int,
        negation_map: Dict[int, int],
        current_step: int,
        axiom_labels: Optional[Dict[int, Any]] = None,
    ) -> Dict[str, Any]:
        """A teljes confidence_score számítás egy (i, j) élre.

        Visszaadja a 4 input-score-t, a nyers értékeket (post-hoc analízishez),
        és a min-aggregált confidence_score-t."""
        cd_score, cd_raw = self.chain_depth_score(A, i, j)
        si_score, si_raw = self.surprise_inverse_score(i, j, axiom_labels)
        sh_score, sh_raw = self.stuck_history_score(current_step, i, j, axiom_labels)
        ci_score, ci_raw = self.contradiction_distance_score(A, i, j, negation_map)
        confidence = min(cd_score, si_score, sh_score, ci_score)
        # Melyik komponens volt a min? (transzparenciához)
        components = {
            "chain_depth": cd_score,
            "surprise_inverse": si_score,
            "stuck_history": sh_score,
            "contradiction_distance": ci_score,
        }
        min_component = min(components, key=components.get)
        return {
            "confidence_score": float(confidence),
            "min_component": min_component,
            "components": components,
            "raw": {
                "chain_depth_n_paths": cd_raw,
                "surprise_raw": si_raw,
                "stuck_raw": sh_raw,
                "contradiction_distance": ci_raw,
            },
        }


def epistemic_label(
    confidence: float,
    surprise_raw: float,
    q1: float,
    q2: float,
    q3: float,
    surprise_median: float,
) -> str:
    """Kvantilis-alapú címkézés.

    proven:             c > q3
    hypothesis:         q2 < c <= q3
    uncertain:          q1 < c <= q2
    near_contradiction: c <= q1 AND surprise > median
    (or "uncertain" if c <= q1 but surprise NOT > median — fallback)
    """
    if confidence > q3:
        return "proven"
    if confidence > q2:
        return "hypothesis"
    if confidence > q1:
        return "uncertain"
    # confidence <= q1
    if surprise_raw > surprise_median:
        return "near_contradiction"
    return "uncertain"  # alacsony confidence, de nem "meglepő": csak bizonytalan
