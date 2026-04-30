"""
emission_logger
===============

Converts ``ThinkStepSnapshot`` instances produced by the AIE engine into
discrete emission records. The records form a stable inter-module contract
consumed by downstream analytics (Markov estimation, Fisher computation, ...).

Schema (per record)
-------------------
::

    {
      "step_id": int,
      "tick": int,
      "emission": "deductive_added" | "abductive_added" | "rejected" | "idle",
      "pair": [int, int] | null,
      "domain_transition": bool,
      "reject_reason": "forbidden" | "negation" | "exists" | null
    }

Mapping from ``ThinkStepSnapshot``
----------------------------------
Mutually exclusive and exhaustive:

1. ``mode == "idle_sparse"`` OR ``i is None`` OR ``j is None``
   -> ``emission = "idle"``, ``pair = null``, ``reject_reason = null``.
2. ``edge_added and verified and not abductive``
   -> ``emission = "deductive_added"``, ``reject_reason = null``.
3. ``edge_added and abductive``
   -> ``emission = "abductive_added"``, ``reject_reason = null``.
4. otherwise (``edge_added is False``)
   -> ``emission = "rejected"``. The ``edge_reject`` field is mapped:
   ``"forbidden" -> "forbidden"``, ``"contradiction" -> "negation"``,
   ``"exists" -> "exists"``, anything else -> ``None``.

``domain_transition`` is ``True`` iff ``axiom_labels[i] != axiom_labels[j]``
and both indices are present in the mapping; otherwise ``False``.

Stdlib only.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


_REJECT_MAP: Dict[str, str] = {
    "forbidden": "forbidden",
    "contradiction": "negation",
    "exists": "exists",
}


class EmissionLogger:
    """Derive, buffer, and optionally persist emission records."""

    def __init__(
        self,
        axiom_labels: Optional[Dict[int, Any]] = None,
        log_path: Optional[Path] = None,
        ring_buffer_size: int = 2000,
    ) -> None:
        self.axiom_labels: Optional[Dict[int, Any]] = axiom_labels
        self.log_path: Optional[Path] = Path(log_path) if log_path is not None else None
        self.ring_buffer_size: int = int(ring_buffer_size)
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=self.ring_buffer_size)

        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ derive

    def _derive_domain_transition(
        self, i: Optional[int], j: Optional[int]
    ) -> bool:
        if self.axiom_labels is None or i is None or j is None:
            return False
        if i not in self.axiom_labels or j not in self.axiom_labels:
            return False
        return self.axiom_labels[i] != self.axiom_labels[j]

    def _derive_record(
        self, step_id: int, tick: int, snapshot: Any
    ) -> Dict[str, Any]:
        mode = getattr(snapshot, "mode", None)
        i = getattr(snapshot, "i", None)
        j = getattr(snapshot, "j", None)
        verified = getattr(snapshot, "verified", None)
        edge_added = bool(getattr(snapshot, "edge_added", False))
        abductive = bool(getattr(snapshot, "abductive", False))
        edge_reject = getattr(snapshot, "edge_reject", None)

        emission: str
        pair: Optional[List[int]]
        reject_reason: Optional[str]

        if mode == "idle_sparse" or i is None or j is None:
            emission = "idle"
            pair = None
            reject_reason = None
        elif edge_added and verified and not abductive:
            emission = "deductive_added"
            pair = [int(i), int(j)]
            reject_reason = None
        elif edge_added and abductive:
            emission = "abductive_added"
            pair = [int(i), int(j)]
            reject_reason = None
        else:
            emission = "rejected"
            pair = [int(i), int(j)]
            reject_reason = _REJECT_MAP.get(edge_reject) if isinstance(edge_reject, str) else None

        domain_transition = self._derive_domain_transition(
            i if pair is not None else None,
            j if pair is not None else None,
        )

        return {
            "step_id": int(step_id),
            "tick": int(tick),
            "emission": emission,
            "pair": pair,
            "domain_transition": bool(domain_transition),
            "reject_reason": reject_reason,
        }

    # ------------------------------------------------------------------ public

    def record(self, step_id: int, tick: int, snapshot: Any) -> Dict[str, Any]:
        """Derive an emission record, buffer it, and optionally persist it."""
        rec = self._derive_record(step_id, tick, snapshot)
        self._buffer.append(rec)

        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        return rec

    def recent(self, n: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return the last ``n`` records (or all if ``n`` is None)."""
        if n is None or n >= len(self._buffer):
            return list(self._buffer)
        if n <= 0:
            return []
        # last n
        return list(self._buffer)[-n:]

    def clear(self) -> None:
        """Empty the in-memory ring buffer. Does not touch the JSONL file."""
        self._buffer.clear()
