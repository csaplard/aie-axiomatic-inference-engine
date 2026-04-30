"""
Real-time Fisher-style path-speed estimator on discrete emissions (AIE).

Context
-------
The AIE engine is gaining a third operating mode beyond waking and daemon: the
"hypnagogic" mode, in which logical rules are relaxed. We want to detect when
the system slides from a quasi-stationary relaxed regime into "deep
hypnagogic chaos" — a phase characterised by a rapidly changing emission
distribution.

Metric
------
The discrete emission alphabet has K = 4 fixed labels (see ``ALPHABET``).
From the most recent ``window_size`` emissions we estimate a K x K Markov
transition matrix T, where

    T[i, j] = P(next = j | current = i)

is the empirical conditional probability with Laplace (add-1) smoothing so
no row is zero.

The path-speed v(N) at step N is the Frobenius distance between the matrix
estimated on the most recent window and the matrix estimated on the
preceding (non-overlapping) window:

    v(N) = || T_{n+1} - T_n ||_F
         = sqrt( sum_{i,j} ( T_{n+1}[i,j] - T_n[i,j] )^2 )

A stationary process gives small v(N); a regime change produces a spike.
The detector flags a transition when v(N) exceeds ``threshold_factor`` times
the rolling median of recent v(N) values.

Real-time use
-------------
Whoever owns the emission stream calls ``update(emission)`` once per record
(after extracting the ``"emission"`` field). ``update`` returns the latest
v(N) when enough data is available, or None otherwise. ``detect_trigger()``
exposes the boolean threshold check for the consumer.

This module depends only on numpy and the standard library.
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import Deque, Optional, Tuple

import numpy as np

ALPHABET: Tuple[str, str, str, str] = (
    "deductive_added",
    "abductive_added",
    "rejected",
    "idle",
)
K: int = len(ALPHABET)
_INDEX = {sym: i for i, sym in enumerate(ALPHABET)}


class FisherRealtime:
    """Rolling Frobenius-distance path-speed estimator on discrete emissions."""

    def __init__(self, window_size: int = 500, history_size: int = 200) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        if history_size < 1:
            raise ValueError("history_size must be >= 1")
        self.window_size: int = int(window_size)
        self.history_size: int = int(history_size)
        # Keep at most 2 * window_size emissions (the two adjacent windows).
        self._buffer: Deque[int] = deque(maxlen=2 * self.window_size)
        self._history: Deque[float] = deque(maxlen=self.history_size)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _transition_matrix(indices: np.ndarray) -> np.ndarray:
        """Laplace-smoothed K x K transition matrix from a sequence of indices."""
        counts = np.zeros((K, K), dtype=np.float64)
        if indices.size >= 2:
            for a, b in zip(indices[:-1], indices[1:]):
                counts[int(a), int(b)] += 1.0
        smoothed = counts + 1.0
        row_sums = smoothed.sum(axis=1, keepdims=True)
        return smoothed / row_sums

    # ------------------------------------------------------------------ public
    def update(self, emission: str) -> Optional[float]:
        """Append one emission and return the new v(N) if computable."""
        if emission not in _INDEX:
            raise ValueError(
                f"Unknown emission {emission!r}; expected one of {ALPHABET}"
            )
        self._buffer.append(_INDEX[emission])

        if len(self._buffer) < 2 * self.window_size:
            return None

        arr = np.fromiter(self._buffer, dtype=np.int64, count=len(self._buffer))
        prev = arr[: self.window_size]
        curr = arr[self.window_size : 2 * self.window_size]
        t_prev = self._transition_matrix(prev)
        t_curr = self._transition_matrix(curr)
        v = float(np.linalg.norm(t_curr - t_prev, ord="fro"))
        self._history.append(v)
        return v

    def current_transition_matrix(self) -> Optional[np.ndarray]:
        """K x K Laplace-smoothed transition matrix on the latest window."""
        if len(self._buffer) < self.window_size:
            return None
        arr = np.fromiter(self._buffer, dtype=np.int64, count=len(self._buffer))
        recent = arr[-self.window_size :]
        return self._transition_matrix(recent)

    def path_speed(self) -> Optional[float]:
        """Most recent v(N), or None if none computed yet."""
        if not self._history:
            return None
        return self._history[-1]

    def path_speed_median(self) -> Optional[float]:
        """Median of the path-speed history (steady-state baseline)."""
        if not self._history:
            return None
        return float(median(self._history))

    def detect_trigger(
        self, threshold_factor: float = 2.0, min_history: int = 20
    ) -> bool:
        """True iff path_speed() > path_speed_median() * threshold_factor and
        we have at least ``min_history`` samples to make the comparison
        meaningful."""
        if len(self._history) < min_history:
            return False
        latest = self.path_speed()
        baseline = self.path_speed_median()
        if latest is None or baseline is None:
            return False
        return latest > baseline * threshold_factor

    def reset(self) -> None:
        """Drop all buffered emissions and path-speed history."""
        self._buffer.clear()
        self._history.clear()
