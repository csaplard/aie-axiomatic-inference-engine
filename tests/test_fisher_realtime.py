"""
Unit tests for ``fisher_realtime.FisherRealtime``.

Verifies the discrete-emission Markov path-speed estimator: input validation,
warm-up behaviour, transition-matrix shape and Laplace smoothing, behaviour on
stationary vs. regime-change synthetic streams, and the trigger / reset API.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fisher_realtime import ALPHABET, FisherRealtime, K


class FisherRealtimeBasicTests(unittest.TestCase):
    def test_unknown_emission_raises(self) -> None:
        """Emissions outside ALPHABET must raise ValueError."""
        fr = FisherRealtime(window_size=10, history_size=5)
        with self.assertRaises(ValueError):
            fr.update("not_a_real_emission")

    def test_update_returns_none_until_enough_data(self) -> None:
        """update returns None until 2 * window_size emissions accumulated."""
        w = 20
        fr = FisherRealtime(window_size=w, history_size=10)
        for i in range(2 * w - 1):
            self.assertIsNone(fr.update(ALPHABET[i % K]))
        # The (2*w)-th update should produce the first numeric v(N).
        v = fr.update(ALPHABET[0])
        self.assertIsNotNone(v)
        self.assertIsInstance(v, float)

    def test_update_returns_finite_nonnegative(self) -> None:
        """After warm-up, v(N) is a finite non-negative float."""
        w = 20
        fr = FisherRealtime(window_size=w, history_size=10)
        for i in range(2 * w + 50):
            v = fr.update(ALPHABET[i % K])
        self.assertIsNotNone(v)
        self.assertTrue(math.isfinite(v))
        self.assertGreaterEqual(v, 0.0)

    def test_current_transition_matrix_shape_and_rows(self) -> None:
        """current_transition_matrix is K x K with rows summing to ~1.0."""
        w = 30
        fr = FisherRealtime(window_size=w, history_size=10)
        rng = np.random.default_rng(0)
        for _ in range(2 * w + 10):
            fr.update(ALPHABET[int(rng.integers(0, K))])
        T = fr.current_transition_matrix()
        self.assertIsNotNone(T)
        self.assertIsInstance(T, np.ndarray)
        self.assertEqual(T.shape, (K, K))
        row_sums = T.sum(axis=1)
        for s in row_sums:
            self.assertAlmostEqual(float(s), 1.0, places=10)
        # Laplace smoothing: every entry must be strictly positive.
        self.assertTrue(np.all(T > 0.0))


class FisherRealtimeSyntheticStreamTests(unittest.TestCase):
    def test_stationary_sequence_low_path_speed(self) -> None:
        """A perfectly cyclic (stationary) emission stream yields low v(N)."""
        w = 50
        fr = FisherRealtime(window_size=w, history_size=200)
        cycle = ("deductive_added", "rejected", "idle", "abductive_added")
        speeds = []
        for i in range(2 * w + 500):
            v = fr.update(cycle[i % len(cycle)])
            if v is not None:
                speeds.append(v)
        # After the buffer fills, neighbouring windows should be (almost)
        # identical, so v(N) should stay clearly below the sanity threshold.
        self.assertGreater(len(speeds), 100)
        # Use the tail (post warm-up) to dodge buffer-edge transients.
        tail = speeds[-200:]
        self.assertLess(max(tail), 0.5)

    def test_regime_change_spikes_path_speed(self) -> None:
        """Switching the underlying pattern causes a v(N) spike clearly
        above the steady-state baseline observed before the boundary."""
        w = 100
        fr = FisherRealtime(window_size=w, history_size=400)
        pre_cycle = ("deductive_added", "rejected")
        post_cycle = ("idle", "abductive_added")

        baseline_speeds = []
        # 1000 emissions of pattern A.
        for i in range(1000):
            v = fr.update(pre_cycle[i % len(pre_cycle)])
            if v is not None:
                baseline_speeds.append(v)
        baseline_max = max(baseline_speeds) if baseline_speeds else 0.0

        # The very first update under pattern B straddles the boundary
        # (the "previous" window now contains B-tail but the older window
        # still contains A) -- that's the v(N) we examine.
        boundary_v = fr.update(post_cycle[0])
        for i in range(1, 50):
            v = fr.update(post_cycle[i % len(post_cycle)])
            # Track the largest v across the boundary region.
            if v is not None and v > boundary_v:
                boundary_v = v

        self.assertIsNotNone(boundary_v)
        # Boundary spike must dominate the steady-state baseline.
        self.assertGreater(boundary_v, baseline_max * 2.0)


class FisherRealtimeTriggerTests(unittest.TestCase):
    def test_detect_trigger_false_before_min_history(self) -> None:
        """detect_trigger stays False while history is shorter than min_history."""
        w = 10
        fr = FisherRealtime(window_size=w, history_size=200)
        # Even with chaotic input, no trigger before min_history v(N) values.
        rng = np.random.default_rng(1)
        for _ in range(2 * w + 5):  # only a few v(N) values produced
            fr.update(ALPHABET[int(rng.integers(0, K))])
        self.assertFalse(fr.detect_trigger(threshold_factor=2.0, min_history=20))

    def test_detect_trigger_true_after_chaos_event(self) -> None:
        """A regime change after a calm steady state triggers detect_trigger."""
        w = 50
        fr = FisherRealtime(window_size=w, history_size=400)
        calm = ("deductive_added", "rejected", "idle", "abductive_added")
        # Long calm period so history fills with small, similar v(N) values.
        for i in range(2 * w + 600):
            fr.update(calm[i % len(calm)])
        self.assertFalse(
            fr.detect_trigger(threshold_factor=2.0, min_history=20),
            "Stationary stream should not trigger.",
        )
        # Inject a sharp regime change.
        chaos = ("idle", "idle", "abductive_added", "deductive_added", "rejected")
        triggered = False
        for i in range(200):
            fr.update(chaos[i % len(chaos)])
            if fr.detect_trigger(threshold_factor=2.0, min_history=20):
                triggered = True
                break
        self.assertTrue(triggered, "Expected detect_trigger to fire after chaos.")

    def test_reset_clears_buffer_and_history(self) -> None:
        """reset removes buffered emissions and history entries."""
        w = 10
        fr = FisherRealtime(window_size=w, history_size=20)
        for i in range(3 * w):
            fr.update(ALPHABET[i % K])
        self.assertIsNotNone(fr.path_speed())
        self.assertIsNotNone(fr.current_transition_matrix())
        fr.reset()
        self.assertIsNone(fr.path_speed())
        self.assertIsNone(fr.path_speed_median())
        self.assertIsNone(fr.current_transition_matrix())
        # After reset, the warm-up requirement applies again.
        self.assertIsNone(fr.update(ALPHABET[0]))


if __name__ == "__main__":
    unittest.main()
