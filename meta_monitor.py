"""
Modul D — PFC-analóg meta-monitor: stuck-detection + intervention.

Két komponens:

1. **StuckDetector**: figyeli az utóbbi `window_size` think_step pár-kísérletét
   (pair vagy domain-pair granularitással), és tüzel, ha bármelyik kulcs
   `repetition_threshold` vagy többször megjelent.

2. **InterventionManager**: ha a detector tüzel, intervenciót indít — jelen
   verzióban hipnagóg epizódot trigger-el az engine-en keresztül.

A komponens **paraméter-érzékeny** (a "stuck" definíciója empirikus). A formális
pre-reg ELŐTT calibration-scan szakaszt kell futtatni, hogy a paraméterek
healthy-zónáját azonosítsuk (firing rate ∈ [0.05, 0.30] a baseline-on).

Schema:
- granularity = "pair": a kulcs (i, j) tuple
- granularity = "domain": a kulcs (domain(i), domain(j)) tuple

Modul B (epizodikus memória) a perzisztens tárolásra használható, de a narrow
scope-ban a detector csak gördülő deque-et használ; a perzisztencia a meglévő
engine.save_state() metóduson keresztül érhető el.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


class StuckDetector:
    """Gördülő ablakos pár-ismétlődés detektor."""

    def __init__(
        self,
        window_size: int = 200,
        repetition_threshold: int = 5,
        granularity: str = "pair",
    ) -> None:
        if granularity not in ("pair", "domain"):
            raise ValueError(f"granularity must be 'pair' or 'domain', got {granularity!r}")
        if window_size < 1 or repetition_threshold < 2:
            raise ValueError("window_size>=1 and repetition_threshold>=2 required")
        self.window_size = int(window_size)
        self.repetition_threshold = int(repetition_threshold)
        self.granularity = granularity
        self._recent: Deque[Tuple] = deque(maxlen=self.window_size)
        self._counts: Counter = Counter()
        self._attempt_count: int = 0
        self._fire_count: int = 0
        self._last_fired_key: Optional[Tuple] = None

    @property
    def attempt_count(self) -> int:
        return self._attempt_count

    @property
    def fire_count(self) -> int:
        return self._fire_count

    def fire_rate(self) -> float:
        if self._attempt_count == 0:
            return 0.0
        return self._fire_count / float(self._attempt_count)

    def reset(self) -> None:
        self._recent.clear()
        self._counts.clear()
        self._attempt_count = 0
        self._fire_count = 0
        self._last_fired_key = None

    def observe(
        self, i: Optional[int], j: Optional[int],
        axiom_labels: Optional[Dict[int, Any]] = None,
    ) -> bool:
        """Új pár-attempt rögzítése. Visszaadja: tüzelt-e ezzel a lépéssel."""
        if i is None or j is None:
            # idle vagy nincs valid pár — nem ismétlődés-jelölt
            self._attempt_count += 1
            return False
        if self.granularity == "domain":
            if axiom_labels is None:
                key = ("UNK", "UNK")
            else:
                di = axiom_labels.get(int(i))
                dj = axiom_labels.get(int(j))
                key = (
                    str(di.value) if hasattr(di, "value") else str(di),
                    str(dj.value) if hasattr(dj, "value") else str(dj),
                )
        else:
            key = (int(i), int(j))

        # Ha a deque tele van, az eldobott kulcsot le kell vonni a counts-ból
        if len(self._recent) == self.window_size:
            old = self._recent[0]
            self._counts[old] -= 1
            if self._counts[old] <= 0:
                del self._counts[old]
        self._recent.append(key)
        self._counts[key] += 1
        self._attempt_count += 1

        cnt = self._counts[key]
        if cnt >= self.repetition_threshold:
            self._fire_count += 1
            self._last_fired_key = key
            return True
        return False

    def last_fired_key(self) -> Optional[Tuple]:
        return self._last_fired_key

    def top_keys(self, k: int = 5) -> List[Tuple[Tuple, int]]:
        """Diagnosztika: a leggyakoribb k kulcs és számuk a jelenlegi ablakban."""
        return self._counts.most_common(k)


class InterventionManager:
    """Ha a detector tüzel, intervenciót indít. Default intervenció: hipnagóg
    epizód (engine.start_hypnagogic_episode())."""

    def __init__(
        self,
        intervention_callback: Optional[Callable[[Tuple], bool]] = None,
        cooldown_steps: int = 100,
    ) -> None:
        """
        intervention_callback(fired_key) -> True ha az intervenció elindult.
                                            Ha None, no-op (csak loggol).
        cooldown_steps: az intervenció után ennyi lépésen belül nem ismétel.
        """
        self._callback = intervention_callback
        self._cooldown = int(cooldown_steps)
        self._cooldown_remaining: int = 0
        self._intervention_count: int = 0
        self._intervention_log: List[Dict[str, Any]] = []

    @property
    def intervention_count(self) -> int:
        return self._intervention_count

    def tick(self, fired: bool, fired_key: Optional[Tuple], step_id: int) -> bool:
        """Egy lépés feldolgozása. Visszaadja: indított-e intervenciót."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return False
        if not fired:
            return False
        # Callback nélkül (log-only mód) nincs aktív intervenció
        if self._callback is None:
            return False
        try:
            ok = bool(self._callback(fired_key))
        except Exception:
            ok = False
        if ok:
            self._intervention_count += 1
            self._intervention_log.append({
                "step_id": int(step_id),
                "fired_key": list(fired_key) if fired_key is not None else None,
            })
            self._cooldown_remaining = self._cooldown
            return True
        return False

    def log(self) -> List[Dict[str, Any]]:
        return list(self._intervention_log)
