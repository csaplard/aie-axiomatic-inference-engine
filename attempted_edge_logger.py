"""
Modul C v2 — attempted-edge tracker.

A confidence_score predikciójának új target változójához: MINDEN attempted élt
logol (rejekt-elteket is), nem csak az ADDED-eket.

Schema (per attempt):
{
  "step_id": int,
  "i": int | null,
  "j": int | null,
  "outcome": "accepted" | "forbidden" | "contradiction" | "exists" | "no_pair",
  "confidence_score": float | null,
  "components": {chain_depth, surprise_inverse, stuck_history, contradiction_distance},
  "raw": {chain_depth_n_paths, surprise_raw, stuck_raw, contradiction_distance_raw},
}

A confidence_score-t az attempted élre számoljuk a PRE-attempt mátrix-állapoton
(tehát szigorúan elválasztva attól, hogy az él hozzáadódott-e).

A modul stateless függvényeket exportál; a tracker maga az engine-be integrálódik.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional


class AttemptedEdgeLogger:
    """In-memory tracker MINDEN attempt-re."""

    def __init__(self, max_records: int = 100000) -> None:
        self._records: Deque[Dict[str, Any]] = deque(maxlen=max_records)

    def __len__(self) -> int:
        return len(self._records)

    def record(self, entry: Dict[str, Any]) -> None:
        self._records.append(dict(entry))

    def all_records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    @staticmethod
    def classify_outcome(snapshot) -> str:
        """A think_step snapshot-ból derive az outcome osztályt."""
        if snapshot.mode == "idle_sparse" or snapshot.i is None or snapshot.j is None:
            return "no_pair"
        if snapshot.edge_added:
            return "accepted"
        rj = snapshot.edge_reject
        if rj == "forbidden":
            return "forbidden"
        if rj == "contradiction":
            return "contradiction"
        if rj == "exists":
            return "exists"
        # Egyéb: "no_hypothesis" stb. (akkor history-szempontból irrelevant)
        return "no_pair"
