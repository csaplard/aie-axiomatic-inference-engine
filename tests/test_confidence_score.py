"""
Modul C — confidence_score unit tesztek.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from confidence_score import ConfidenceComputer, epistemic_label


class ChainDepthScoreTests(unittest.TestCase):
    def test_no_paths_zero_score(self) -> None:
        cc = ConfidenceComputer(chain_depth_cap=5)
        n = 5
        A = np.eye(n, dtype=np.float64)
        # Nincs köztes csúcs — nincs út
        score, n_paths = cc.chain_depth_score(A, 0, 1)
        self.assertEqual(n_paths, 0)
        self.assertEqual(score, 0.0)

    def test_full_paths_score_one(self) -> None:
        cc = ConfidenceComputer(chain_depth_cap=3)
        n = 6
        A = np.eye(n, dtype=np.float64)
        # 0 -> {2, 3, 4, 5} -> 1: 4 köztes út, cap=3 → score=1.0
        for k in [2, 3, 4, 5]:
            A[0, k] = 1.0
            A[k, 1] = 1.0
        score, n_paths = cc.chain_depth_score(A, 0, 1)
        self.assertEqual(score, 1.0)
        # n_paths a cap-nél áll meg
        self.assertEqual(n_paths, 3)

    def test_partial_paths_score(self) -> None:
        cc = ConfidenceComputer(chain_depth_cap=5)
        n = 5
        A = np.eye(n, dtype=np.float64)
        # 0 -> 2 -> 1: csak 1 köztes
        A[0, 2] = 1.0
        A[2, 1] = 1.0
        score, n_paths = cc.chain_depth_score(A, 0, 1)
        self.assertEqual(n_paths, 1)
        self.assertAlmostEqual(score, 0.2)


class SurpriseInverseTests(unittest.TestCase):
    def test_unseen_pair_low_score(self) -> None:
        cc = ConfidenceComputer(recent_window=100, laplace_k=10, surprise_norm=6.0)
        # Töltsük fel a recent-et más párokkal
        for _ in range(50):
            cc.observe_pair(2, 3)
        # (0, 1) sosem volt → magas surprise → alacsony score
        score, raw = cc.surprise_inverse_score(0, 1)
        # surprise_raw nagyobb mint 0
        self.assertGreater(raw, 0.0)
        self.assertLess(score, 1.0)

    def test_frequent_pair_high_score(self) -> None:
        cc = ConfidenceComputer(recent_window=100, laplace_k=10, surprise_norm=6.0)
        # (0, 1) sokszor → alacsony surprise → magas score
        for _ in range(80):
            cc.observe_pair(0, 1)
        score, raw = cc.surprise_inverse_score(0, 1)
        # P((0,1)) ~ 80/(100+10), magas → surprise alacsony → score magas
        self.assertGreater(score, 0.85)

    def test_recent_window_eviction(self) -> None:
        cc = ConfidenceComputer(recent_window=5, laplace_k=2, surprise_norm=3.0)
        for _ in range(5):
            cc.observe_pair(0, 1)
        # Most a (0,1) count = 5, total = 5
        s1, _ = cc.surprise_inverse_score(0, 1)
        # Töltsük tele más párral
        for _ in range(5):
            cc.observe_pair(2, 3)
        # (0,1) most már nincs a recent-ben → magas surprise → alacsony score
        s2, _ = cc.surprise_inverse_score(0, 1)
        self.assertGreater(s1, s2)


class StuckHistoryTests(unittest.TestCase):
    def test_no_stuck_score_one(self) -> None:
        cc = ConfidenceComputer(stuck_decay=0.01, stuck_norm=5.0)
        score, raw = cc.stuck_history_score(current_step=100, i=0, j=1)
        self.assertEqual(raw, 0.0)
        self.assertEqual(score, 1.0)

    def test_recent_stuck_lowers_score(self) -> None:
        cc = ConfidenceComputer(stuck_decay=0.01, stuck_norm=5.0)
        # Néhány stuck esemény (0, 1)-re
        for step in [50, 70, 90]:
            cc.observe_stuck_event(step, (0, 1))
        score, raw = cc.stuck_history_score(current_step=100, i=0, j=1)
        self.assertGreater(raw, 0.0)
        self.assertLess(score, 1.0)

    def test_old_stuck_decays(self) -> None:
        cc = ConfidenceComputer(stuck_decay=0.05, stuck_norm=5.0)
        # Nagyon régi esemény
        cc.observe_stuck_event(0, (0, 1))
        score_far, raw_far = cc.stuck_history_score(current_step=1000, i=0, j=1)
        # Friss esemény
        cc2 = ConfidenceComputer(stuck_decay=0.05, stuck_norm=5.0)
        cc2.observe_stuck_event(990, (0, 1))
        score_near, raw_near = cc2.stuck_history_score(current_step=1000, i=0, j=1)
        # Friss → magasabb raw, alacsonyabb score
        self.assertGreater(raw_near, raw_far)
        self.assertLess(score_near, score_far)

    def test_different_key_no_match(self) -> None:
        cc = ConfidenceComputer(stuck_decay=0.01, stuck_norm=5.0)
        cc.observe_stuck_event(50, (2, 3))
        # (0, 1) sosem volt stuck
        score, raw = cc.stuck_history_score(current_step=100, i=0, j=1)
        self.assertEqual(raw, 0.0)


class ContradictionDistanceTests(unittest.TestCase):
    def test_no_negation_pair_score_one(self) -> None:
        cc = ConfidenceComputer(dist_norm=10.0)
        A = np.eye(5, dtype=np.float64)
        # j=2-nek nincs negation pair-je
        score, d = cc.contradiction_distance_score(A, i=0, j=2, negation_map={})
        self.assertEqual(score, 1.0)

    def test_far_distance_score_one(self) -> None:
        cc = ConfidenceComputer(dist_norm=2.0)
        A = np.eye(5, dtype=np.float64)
        # j=1 → neg(j)=2, de nincs út → distance = inf → score = 1.0
        neg_map = {1: 2, 2: 1}
        score, d = cc.contradiction_distance_score(A, i=0, j=1, negation_map=neg_map)
        self.assertEqual(score, 1.0)

    def test_close_distance_low_score(self) -> None:
        cc = ConfidenceComputer(dist_norm=10.0)
        A = np.eye(5, dtype=np.float64)
        # j=1 → neg(j)=2, és van út 1 → 2 (1 lépés)
        A[1, 2] = 1.0
        neg_map = {1: 2, 2: 1}
        score, d = cc.contradiction_distance_score(A, i=0, j=1, negation_map=neg_map)
        self.assertEqual(d, 1.0)
        self.assertAlmostEqual(score, 0.1)

    def test_excludes_self_edge(self) -> None:
        cc = ConfidenceComputer(dist_norm=10.0)
        A = np.eye(5, dtype=np.float64)
        # 0 → 1 él létezik; j=1, neg(j)=2; van egy út 1 → 2
        A[0, 1] = 1.0
        A[1, 2] = 1.0
        neg_map = {1: 2}
        # Az exclude=(0, 1) él irreleváns, mert a path j(=1) → neg_j(=2) megy
        score, d = cc.contradiction_distance_score(A, i=0, j=1, negation_map=neg_map)
        self.assertEqual(d, 1.0)


class ComputeIntegrationTests(unittest.TestCase):
    def test_compute_returns_full_dict(self) -> None:
        cc = ConfidenceComputer(chain_depth_cap=5)
        n = 5
        A = np.eye(n, dtype=np.float64)
        result = cc.compute(A, 0, 1, negation_map={}, current_step=10)
        self.assertIn("confidence_score", result)
        self.assertIn("min_component", result)
        self.assertIn("components", result)
        self.assertIn("raw", result)
        # 4 komponens
        self.assertEqual(set(result["components"].keys()), {
            "chain_depth", "surprise_inverse", "stuck_history", "contradiction_distance",
        })

    def test_min_aggregation_correctly_finds_min(self) -> None:
        cc = ConfidenceComputer(
            chain_depth_cap=5, recent_window=100, surprise_norm=2.0,
            stuck_decay=0.01, stuck_norm=5.0, dist_norm=20.0,
        )
        A = np.eye(5, dtype=np.float64)
        # j=1, neg(j)=2, és A[1,2]=1 → contradiction_distance close → low score
        A[1, 2] = 1.0
        # Magas chain_depth: 0 → {3, 4} → 1
        A[0, 3] = 1.0; A[3, 1] = 1.0
        A[0, 4] = 1.0; A[4, 1] = 1.0
        result = cc.compute(A, 0, 1, negation_map={1: 2}, current_step=10)
        # Várt: contradiction_distance a min komponens
        self.assertEqual(result["min_component"], "contradiction_distance")


class EpistemicLabelTests(unittest.TestCase):
    def test_proven(self) -> None:
        label = epistemic_label(0.9, 0.0, q1=0.2, q2=0.5, q3=0.8, surprise_median=2.0)
        self.assertEqual(label, "proven")

    def test_hypothesis(self) -> None:
        label = epistemic_label(0.6, 0.0, q1=0.2, q2=0.5, q3=0.8, surprise_median=2.0)
        self.assertEqual(label, "hypothesis")

    def test_uncertain(self) -> None:
        label = epistemic_label(0.3, 0.0, q1=0.2, q2=0.5, q3=0.8, surprise_median=2.0)
        self.assertEqual(label, "uncertain")

    def test_near_contradiction(self) -> None:
        # Alacsony c ÉS magas surprise
        label = epistemic_label(0.1, 5.0, q1=0.2, q2=0.5, q3=0.8, surprise_median=2.0)
        self.assertEqual(label, "near_contradiction")

    def test_low_c_low_surprise_uncertain(self) -> None:
        # Alacsony c DE alacsony surprise → fallback uncertain
        label = epistemic_label(0.1, 0.5, q1=0.2, q2=0.5, q3=0.8, surprise_median=2.0)
        self.assertEqual(label, "uncertain")


if __name__ == "__main__":
    unittest.main()
