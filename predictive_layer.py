"""
Modul E (egyszerűsített) — L1 predictive layer: domain-pair EMA rules.

A predictive coding L0 + L1 architektúra:
  L0 = facts (engine attempted edges, outcome ∈ {accepted, contradiction, forbidden, ...})
  L1 = domain-pair rules (EMA-frissített P(accepted | (D_a, D_b)))

A modul két objektumot ad:
  - `L1RuleSet`: a rule-tár (domain-pair rule values), train/freeze módokkal
  - `GlobalRule`: a baseline (single-rule, single accept-rate, EMA)

Mindkettő prediktív: predict(D_a, D_b) → [0, 1] valószínűség az accepted-re.

Az engine-be NEM hat — csak megfigyel és tanul. A tesztek a Brier-score-ot
mérik a tényleges outcome-okhoz képest.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _domain_key(d: Any) -> str:
    """Domain → string kulcs (Enum vagy str). Tolerans None-ra."""
    if d is None:
        return "UNK"
    return str(d.value) if hasattr(d, "value") else str(d)


class L1RuleSet:
    """Domain-pair EMA rules. Külön rule per (D_a, D_b) pár."""

    def __init__(self, alpha: float = 0.10, init_value: float = 0.5) -> None:
        if not (0.0 < alpha < 1.0):
            raise ValueError("alpha must be in (0, 1)")
        if not (0.0 <= init_value <= 1.0):
            raise ValueError("init_value must be in [0, 1]")
        self.alpha = float(alpha)
        self.init_value = float(init_value)
        self._rules: Dict[Tuple[str, str], float] = {}
        self._update_count: Dict[Tuple[str, str], int] = {}
        self._last_delta: Optional[float] = None
        self._frozen: bool = False
        # update_history: list of (key, pre_value, post_value, delta) — diagnosztikához
        self._update_history: list = []

    def freeze(self) -> None:
        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def predict(self, d_a: Any, d_b: Any) -> float:
        """Visszaadja a (D_a, D_b)-re tárolt rule értéket; ha nincs, init_value."""
        key = (_domain_key(d_a), _domain_key(d_b))
        return self._rules.get(key, self.init_value)

    def update(self, d_a: Any, d_b: Any, outcome_accepted: bool) -> Optional[float]:
        """EMA frissítés: rule ← α * y + (1-α) * rule.

        Visszaadja a delta-t, vagy None ha frozen.
        """
        if self._frozen:
            return None
        key = (_domain_key(d_a), _domain_key(d_b))
        pre = self._rules.get(key, self.init_value)
        y = 1.0 if outcome_accepted else 0.0
        post = self.alpha * y + (1.0 - self.alpha) * pre
        self._rules[key] = post
        self._update_count[key] = self._update_count.get(key, 0) + 1
        delta = post - pre
        self._last_delta = delta
        self._update_history.append((key, pre, post, delta))
        return float(delta)

    def num_rules(self) -> int:
        return len(self._rules)

    def update_count(self, d_a: Any, d_b: Any) -> int:
        return self._update_count.get((_domain_key(d_a), _domain_key(d_b)), 0)

    def total_updates(self) -> int:
        return sum(self._update_count.values())

    def all_rules(self) -> Dict[Tuple[str, str], float]:
        return dict(self._rules)

    def update_history(self) -> list:
        return list(self._update_history)


class GlobalRule:
    """Single-rule baseline: egyetlen accept-rate átlag, EMA-frissítve.

    Az E-H2 specificity-test baseline-jaként szolgál: ha az L1-domain-pair
    nem ad jobb predikciót mint ez, a rétegzés felesleges."""

    def __init__(self, alpha: float = 0.10, init_value: float = 0.5) -> None:
        if not (0.0 < alpha < 1.0):
            raise ValueError("alpha must be in (0, 1)")
        self.alpha = float(alpha)
        self._value = float(init_value)
        self._frozen = False
        self._update_count: int = 0

    def freeze(self) -> None:
        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def value(self) -> float:
        return self._value

    def predict(self, d_a: Any = None, d_b: Any = None) -> float:
        """Same value irrespective of domain pair."""
        return self._value

    def update(self, d_a: Any, d_b: Any, outcome_accepted: bool) -> Optional[float]:
        if self._frozen:
            return None
        y = 1.0 if outcome_accepted else 0.0
        pre = self._value
        post = self.alpha * y + (1.0 - self.alpha) * pre
        self._value = post
        self._update_count += 1
        return post - pre


def brier_score(predictions: list, actuals: list) -> float:
    """Brier score: mean over (pred - actual)²."""
    if not predictions or len(predictions) != len(actuals):
        return float("nan")
    n = len(predictions)
    s = sum((float(p) - float(a)) ** 2 for p, a in zip(predictions, actuals))
    return s / n
