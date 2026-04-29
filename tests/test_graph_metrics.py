"""
graph_metrics tesztek: topological_depth (DAG + SCC kondenzátum),
asymmetry_ratio, reverse_rejection_rate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph_metrics import (
    asymmetry_ratio,
    reverse_rejection_rate,
    topological_depth,
)


class TopologicalDepthTests(unittest.TestCase):
    def test_empty_edges_returns_one(self) -> None:
        # Csak diagonális (önhivatkozás) — 0 él offdiag
        A = np.eye(5, dtype=np.float64)
        self.assertEqual(topological_depth(A), 1)

    def test_simple_chain_depth_equals_length(self) -> None:
        A = np.eye(4, dtype=np.float64)
        A[0, 1] = A[1, 2] = A[2, 3] = 1.0
        # 4 csúcs láncban → leghosszabb út csúcsszáma = 4
        self.assertEqual(topological_depth(A), 4)

    def test_dag_branching(self) -> None:
        A = np.eye(5, dtype=np.float64)
        # 0 -> 1 -> 3, 0 -> 2 -> 3, 3 -> 4
        A[0, 1] = A[1, 3] = A[0, 2] = A[2, 3] = A[3, 4] = 1.0
        # leghosszabb: 0->1->3->4 vagy 0->2->3->4 = 4 csúcs
        self.assertEqual(topological_depth(A), 4)

    def test_cycle_uses_scc_weight(self) -> None:
        # 3-as kör: SCC kondenzátum egyetlen csomópont, súly = 3
        A = np.eye(3, dtype=np.float64)
        A[0, 1] = A[1, 2] = A[2, 0] = 1.0
        self.assertEqual(topological_depth(A), 3)

    def test_diagonal_ignored(self) -> None:
        # i->i nem számít él
        A = np.eye(3, dtype=np.float64) * 5.0
        self.assertEqual(topological_depth(A), 1)


class AsymmetryRatioTests(unittest.TestCase):
    def test_no_edges_returns_one(self) -> None:
        A = np.eye(4, dtype=np.float64)
        self.assertEqual(asymmetry_ratio(A), 1.0)

    def test_fully_symmetric_returns_zero(self) -> None:
        A = np.eye(3, dtype=np.float64)
        # minden i->j fordítva is megvan
        A[0, 1] = A[1, 0] = 1.0
        A[1, 2] = A[2, 1] = 1.0
        A[0, 2] = A[2, 0] = 1.0
        self.assertEqual(asymmetry_ratio(A), 0.0)

    def test_fully_asymmetric_returns_one(self) -> None:
        A = np.eye(3, dtype=np.float64)
        A[0, 1] = A[1, 2] = A[0, 2] = 1.0
        self.assertEqual(asymmetry_ratio(A), 1.0)

    def test_half_symmetric(self) -> None:
        A = np.eye(3, dtype=np.float64)
        A[0, 1] = A[1, 0] = 1.0  # szimmetrikus pár
        A[0, 2] = 1.0            # csak egyirányú
        # 3 él: 2 szimm párból, 1 aszim → 1/3
        self.assertAlmostEqual(asymmetry_ratio(A), 1.0 / 3.0, places=6)


class ReverseRejectionRateTests(unittest.TestCase):
    def test_zero_attempts_returns_zero(self) -> None:
        self.assertEqual(reverse_rejection_rate(0, 0), 0.0)

    def test_normal_ratio(self) -> None:
        self.assertAlmostEqual(reverse_rejection_rate(10, 3), 0.3)

    def test_clamped_to_one(self) -> None:
        # Ha rejects > attempts (érvénytelen, de védett)
        self.assertEqual(reverse_rejection_rate(5, 10), 1.0)


if __name__ == "__main__":
    unittest.main()
