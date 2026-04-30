"""
Modul D — meta-monitor unit tesztek.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from meta_monitor import InterventionManager, StuckDetector


class StuckDetectorTests(unittest.TestCase):
    def test_constructor_validation(self) -> None:
        with self.assertRaises(ValueError):
            StuckDetector(granularity="invalid")
        with self.assertRaises(ValueError):
            StuckDetector(window_size=0)
        with self.assertRaises(ValueError):
            StuckDetector(repetition_threshold=1)

    def test_no_fire_below_threshold(self) -> None:
        det = StuckDetector(window_size=10, repetition_threshold=5)
        # 4 ismétlés ne tüzeljen
        for _ in range(4):
            fired = det.observe(0, 1)
            self.assertFalse(fired)

    def test_fires_at_threshold(self) -> None:
        det = StuckDetector(window_size=10, repetition_threshold=3)
        det.observe(0, 1)
        det.observe(0, 1)
        fired = det.observe(0, 1)  # 3rd time
        self.assertTrue(fired)
        self.assertEqual(det.fire_count, 1)

    def test_continues_to_fire_while_above_threshold(self) -> None:
        """Minden további ismétlés tüzel, amíg az ablakon belül van >= threshold."""
        det = StuckDetector(window_size=10, repetition_threshold=3)
        for k in range(5):
            fired = det.observe(0, 1)
        self.assertEqual(det.fire_count, 3)  # 3rd, 4th, 5th attempt fires

    def test_window_eviction_lowers_count(self) -> None:
        det = StuckDetector(window_size=3, repetition_threshold=3)
        det.observe(0, 1)
        det.observe(0, 1)
        det.observe(0, 1)  # fires
        # Push out the oldest occurrence
        det.observe(2, 3)  # window now: [(0,1), (0,1), (2,3)]
        det.observe(2, 3)  # window: [(0,1), (2,3), (2,3)]
        det.observe(2, 3)  # window: [(2,3), (2,3), (2,3)] — fires
        self.assertEqual(det.fire_count, 2)

    def test_idle_observations_dont_trigger(self) -> None:
        det = StuckDetector(window_size=10, repetition_threshold=3)
        for _ in range(5):
            fired = det.observe(None, None)
        self.assertEqual(det.fire_count, 0)
        self.assertEqual(det.attempt_count, 5)

    def test_domain_granularity(self) -> None:
        det = StuckDetector(window_size=10, repetition_threshold=3, granularity="domain")
        labels = {0: "X", 1: "Y", 2: "X", 3: "Y", 4: "Z"}
        # Mind (X, Y) domain-pár
        for (i, j) in [(0, 1), (2, 3), (0, 1)]:
            fired = det.observe(i, j, axiom_labels=labels)
        self.assertTrue(fired)  # 3rd (X,Y)

    def test_fire_rate(self) -> None:
        det = StuckDetector(window_size=20, repetition_threshold=3)
        for _ in range(10):
            det.observe(0, 1)
        # 10 attempts, fires from 3rd onwards = 8 fires
        self.assertEqual(det.attempt_count, 10)
        self.assertEqual(det.fire_count, 8)
        self.assertAlmostEqual(det.fire_rate(), 0.8)

    def test_top_keys(self) -> None:
        det = StuckDetector(window_size=20, repetition_threshold=10)
        for _ in range(5):
            det.observe(0, 1)
        for _ in range(3):
            det.observe(2, 3)
        top = det.top_keys(5)
        self.assertEqual(top[0], ((0, 1), 5))
        self.assertEqual(top[1], ((2, 3), 3))

    def test_reset(self) -> None:
        det = StuckDetector(window_size=10, repetition_threshold=3)
        for _ in range(5):
            det.observe(0, 1)
        self.assertGreater(det.fire_count, 0)
        det.reset()
        self.assertEqual(det.fire_count, 0)
        self.assertEqual(det.attempt_count, 0)


class InterventionManagerTests(unittest.TestCase):
    def test_no_intervention_when_not_fired(self) -> None:
        called = []
        mgr = InterventionManager(intervention_callback=lambda k: called.append(k) or True)
        mgr.tick(fired=False, fired_key=None, step_id=1)
        self.assertEqual(len(called), 0)

    def test_intervention_when_fired(self) -> None:
        called = []
        mgr = InterventionManager(
            intervention_callback=lambda k: (called.append(k), True)[1],
            cooldown_steps=0,
        )
        mgr.tick(fired=True, fired_key=(1, 2), step_id=1)
        self.assertEqual(called, [(1, 2)])
        self.assertEqual(mgr.intervention_count, 1)

    def test_cooldown_blocks_immediate_repeat(self) -> None:
        called = []
        mgr = InterventionManager(
            intervention_callback=lambda k: (called.append(k), True)[1],
            cooldown_steps=5,
        )
        mgr.tick(fired=True, fired_key=(1, 2), step_id=1)
        for s in range(2, 7):
            mgr.tick(fired=True, fired_key=(3, 4), step_id=s)
        # Csak 1 intervenció, mert a cooldown blokkol
        self.assertEqual(mgr.intervention_count, 1)
        # 6. lépés után: cooldown lejár
        mgr.tick(fired=True, fired_key=(5, 6), step_id=7)
        self.assertEqual(mgr.intervention_count, 2)

    def test_callback_returning_false_does_not_count(self) -> None:
        mgr = InterventionManager(
            intervention_callback=lambda k: False,
            cooldown_steps=0,
        )
        mgr.tick(fired=True, fired_key=(1, 2), step_id=1)
        self.assertEqual(mgr.intervention_count, 0)


class EngineMetaMonitorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mm_int_"))

    def _engine(self, hypnagogic_enabled: bool = False):
        from axiom_kernel import AxiomaticInferenceEngine
        data = {
            "discovery": {
                "enabled": True, "daemon_mode": True, "seed_hamilton_ring": False,
                "ignore_forbidden_edges": False, "ignore_negation_contradictions": False,
                "telemetry_enabled": False,
                "telemetry_log_path": str(self.tmpdir / "tel"),
                "log_path": str(self.tmpdir / "disc"),
                "random_seed": 0,
                "hypnagogic": {
                    "enabled": hypnagogic_enabled,
                    "log_path": str(self.tmpdir / "hyp.jsonl"),
                },
            }
        }
        import tempfile as _tf
        tf = _tf.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
        yaml.safe_dump(data, tf)
        tf.close()
        registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=tf.name, registry_path=str(registry),
        )
        return eng

    def test_attach_log_only_no_hypnagogic(self) -> None:
        """log_only mode: a detector observe-ol, de nem indít intervenciót."""
        eng = self._engine(hypnagogic_enabled=False)
        det = StuckDetector(window_size=20, repetition_threshold=3, granularity="domain")
        eng.attach_meta_monitor(det, intervention_mode="log_only")
        for _ in range(100):
            eng.think_step()
        # A detector legalább 100 attempt-et megfigyelt (= n_steps)
        self.assertGreater(det.attempt_count, 0)
        # log_only mode → 0 intervenció
        self.assertEqual(eng._intervention_manager.intervention_count, 0)

    def test_attach_hypnagogic_intervention(self) -> None:
        """hypnagogic mode: stuck → hipnagóg epizód indítás (ha tüzel)."""
        eng = self._engine(hypnagogic_enabled=True)
        # Nagyon érzékeny detector — biztosan tüzeljen
        det = StuckDetector(window_size=10, repetition_threshold=2, granularity="domain")
        eng.attach_meta_monitor(det, intervention_mode="hypnagogic", cooldown_steps=10)
        for _ in range(200):
            eng.think_step()
        # Várt: legalább 1 intervenció (érzékeny detector miatt)
        self.assertGreater(eng._intervention_manager.intervention_count, 0)

    def test_detach(self) -> None:
        eng = self._engine()
        det = StuckDetector(window_size=10, repetition_threshold=3)
        eng.attach_meta_monitor(det, intervention_mode="log_only")
        self.assertIsNotNone(eng._stuck_detector)
        eng.detach_meta_monitor()
        self.assertIsNone(eng._stuck_detector)


if __name__ == "__main__":
    unittest.main()
