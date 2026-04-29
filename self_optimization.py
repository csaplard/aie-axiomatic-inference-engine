"""
Self-Optimization (Q-stabil utáni) javaslatok: ritka mátrix, ütemezés, B effektív növelése.
A modul nem módosítja futás közben a kódot — csak strukturált javaslatokat ad a fejlesztőnek / ügynöknek.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np


@dataclass
class SystemMetrics:
    """Pillanatkép a motorról (O(1) számolható mezők)."""

    q: float
    q_threshold: float
    n_nodes: int
    nnz_offdiag: int
    backend_efficiency_b: float
    sleep_s: float
    think_steps_per_sec: float = 0.0
    domain_distance_macro_micro: Optional[float] = None
    # „Idő nyila” / falszifikációs labor (lásd THEORY.md, graph_metrics.py)
    topological_depth: int = 0
    asymmetry_ratio: float = 0.0
    reverse_rejection_rate: float = 0.0
    reverse_attempts: int = 0
    reverse_rejects_contradiction: int = 0


@dataclass
class OptimizationSuggestion:
    """Egy javasolt lépés (meta-szint, nem automatikus patch)."""

    category: str
    detail: str
    priority: int
    suggested_b_delta: float  # 0 ha nincs B-módosítás

    def as_line(self) -> str:
        bd = f" dB={self.suggested_b_delta:+.4f}" if self.suggested_b_delta else ""
        return f"[P{self.priority}] {self.category}: {self.detail}{bd}"


@dataclass
class SelfOptimizationAdvisor:
    """
    Ha Q tartósan a küszöb felett van, a rendszer „felesleges” munkát kereshet
    (sűrűség vs. tárolás, alvás vs. áteresztőképesség).
    """

    q_threshold: float
    stable_window: int = 20
    min_samples_for_b_boost: int = 15
    sparsity_nnz_ratio_threshold: float = 0.12
    max_b: float = 1.0
    b_boost_on_stable_q: float = 0.02
    suggest_sparse_backend: bool = True
    policy: Optional[object] = None

    _q_samples: Deque[float] = field(default_factory=lambda: deque(maxlen=256))
    _timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=256))
    _last_step_times: Deque[float] = field(default_factory=lambda: deque(maxlen=64))

    def sync_from_policy(self, policy: Optional[object] = None) -> None:
        """PolicyManager mezők másolása (hot-reload után hívható)."""
        pm = policy or self.policy
        if pm is None:
            return
        self.q_threshold = float(pm.q_threshold_base)
        self.stable_window = int(pm.window_size)
        self.min_samples_for_b_boost = max(3, int(pm.window_size) - 2)
        self.sparsity_nnz_ratio_threshold = float(pm.nnz_ratio_threshold)
        self.suggest_sparse_backend = bool(pm.suggest_sparse_backend)
        self.max_b = float(pm.b_max_limit)
        self.b_boost_on_stable_q = float(pm.b_boost_on_stable_q)

    def record(self, metrics: SystemMetrics) -> None:
        """Minden Q-minta vagy gondolkodási ciklus után hívható."""
        now = time.monotonic()
        self._q_samples.append(metrics.q)
        self._timestamps.append(now)

    def record_think_step(self) -> None:
        """think_step hívások között időbélyeg (áteresztés becsléséhez)."""
        self._last_step_times.append(time.monotonic())

    def think_steps_per_second(self) -> float:
        if len(self._last_step_times) < 2:
            return 0.0
        dt = self._last_step_times[-1] - self._last_step_times[0]
        if dt <= 1e-9:
            return 0.0
        return (len(self._last_step_times) - 1) / dt

    def _q_stable_above_threshold(self) -> bool:
        if len(self._q_samples) < self.stable_window:
            return False
        tail = list(self._q_samples)[-self.stable_window :]
        return all(q >= self.q_threshold for q in tail)

    def matrix_nnz_offdiag(self, matrix: np.ndarray) -> int:
        m = np.asarray(matrix, dtype=np.float64).copy()
        np.fill_diagonal(m, 0.0)
        return int(np.count_nonzero(m))

    def suggest_sparse_representation(self, n_nodes: int, nnz_offdiag: int) -> Optional[OptimizationSuggestion]:
        """Ha a mátrix effektíve ritka, a sűrű tárolás pazarol."""
        if n_nodes <= 1:
            return None
        cap = n_nodes * (n_nodes - 1)
        ratio = nnz_offdiag / max(cap, 1)
        if ratio > self.sparsity_nnz_ratio_threshold:
            return None
        return OptimizationSuggestion(
            category="sparse_storage",
            detail=(
                f"Off-diagonal fill ratio {ratio:.4f} < {self.sparsity_nnz_ratio_threshold}; "
                "consider scipy.sparse.csr_matrix or dedicated edge list for BFS/transitive closure."
            ),
            priority=2,
            suggested_b_delta=0.0,
        )

    def suggest_schedule_tuning(self, sleep_s: float, q: float) -> Optional[OptimizationSuggestion]:
        """Magas Q mellett a gondolkodási hurok alvását finomítani lehet."""
        if sleep_s <= 0:
            return None
        if q < self.q_threshold:
            return None
        tps = self.think_steps_per_second()
        if tps > 0 and tps < 5.0 and sleep_s > 0.002:
            return OptimizationSuggestion(
                category="scheduling",
                detail=(
                    f"Q stable high; think_step rate ~{tps:.1f}/s; "
                    "try reducing sleep_s or batching verify_logic checks to reduce idle time."
                ),
                priority=3,
                suggested_b_delta=0.0,
            )
        if tps > 200.0 and sleep_s < 0.0005:
            return OptimizationSuggestion(
                category="scheduling",
                detail=(
                    f"think_step rate very high ({tps:.0f}/s); consider larger sleep_s to cap CPU on laptop."
                ),
                priority=4,
                suggested_b_delta=0.0,
            )
        return None

    def suggest_backend_efficiency_raise(self, current_b: float) -> Optional[OptimizationSuggestion]:
        """Strukturális stabilitás (Q) után a B meta-paraméter óvatos emelése N* javítására."""
        if not self._q_stable_above_threshold():
            return None
        if len(self._q_samples) < self.min_samples_for_b_boost:
            return None
        if current_b >= self.max_b - 1e-12:
            return None
        delta = min(self.b_boost_on_stable_q, self.max_b - current_b)
        if delta <= 0:
            return None
        return OptimizationSuggestion(
            category="backend_efficiency",
            detail=(
                "Q has been >= threshold for a sustained window; "
                "raise backend_efficiency_b slightly (models trust in compute budget / N*)."
            ),
            priority=1,
            suggested_b_delta=delta,
        )

    def collect_suggestions(
        self,
        metrics: SystemMetrics,
        knowledge_matrix: Optional[np.ndarray] = None,
    ) -> List[OptimizationSuggestion]:
        """Összes aktuális javaslat."""
        out: List[OptimizationSuggestion] = []
        if knowledge_matrix is not None and self.suggest_sparse_backend:
            nnz = metrics.nnz_offdiag
            s = self.suggest_sparse_representation(metrics.n_nodes, nnz)
            if s:
                out.append(s)
        t = self.suggest_schedule_tuning(metrics.sleep_s, metrics.q)
        if t:
            out.append(t)
        b = self.suggest_backend_efficiency_raise(metrics.backend_efficiency_b)
        if b:
            out.append(b)
        out.sort(key=lambda x: x.priority)
        return out

    def apply_suggested_b_delta(
        self, current_b: float, suggestions: List[OptimizationSuggestion]
    ) -> float:
        """Összevonja a B javasolt növeléseit (max 1.0)."""
        d = sum(s.suggested_b_delta for s in suggestions)
        return min(self.max_b, current_b + d)

    def format_report_ascii(self, suggestions: List[OptimizationSuggestion]) -> str:
        """Egy blokk szöveg a kijelzőre."""
        if not suggestions:
            return "[Self-Optimization] No suggestions (Q not stable or already optimal)."
        lines = [
            "[Self-Optimization] Suggestions:",
            f"  Q stable above threshold: {self._q_stable_above_threshold()}",
        ]
        for s in suggestions:
            lines.append(f"  {s.as_line()}")
        return "\n".join(lines)
