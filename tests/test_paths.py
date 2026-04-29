"""
BFS irányítottság, shortest_path, calculate_domain_distance tesztek.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine


def _bare(n: int) -> AxiomaticInferenceEngine:
    eng = AxiomaticInferenceEngine(n_nodes=n, use_axiom_registry=False)
    eng.knowledge_matrix = np.eye(n, dtype=np.float64)
    return eng


class PathTests(unittest.TestCase):
    def test_shortest_path_simple_chain(self) -> None:
        eng = _bare(5)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        eng.knowledge_matrix[2, 3] = 1.0
        path = eng.shortest_path(0, 3)
        self.assertEqual(path, [0, 1, 2, 3])

    def test_shortest_path_directional(self) -> None:
        eng = _bare(4)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        # 2 -> 0 nem létezik fordítva
        self.assertIsNone(eng.shortest_path(2, 0))

    def test_shortest_path_self(self) -> None:
        eng = _bare(3)
        self.assertEqual(eng.shortest_path(1, 1), [1])

    def test_shortest_path_no_route(self) -> None:
        eng = _bare(4)
        eng.knowledge_matrix[0, 1] = 1.0
        # 0 és 3 között nincs út
        self.assertIsNone(eng.shortest_path(0, 3))

    def test_has_path_directional(self) -> None:
        eng = _bare(3)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        self.assertTrue(eng.has_path(0, 2))
        self.assertFalse(eng.has_path(2, 0))


class DomainDistanceTests(unittest.TestCase):
    def setUp(self) -> None:
        # 3 csúcs különböző domainekkel
        reg = {
            "version": "test",
            "nodes": [
                {"id": "macro1", "domain": "MACRO", "formula": "", "variables": [], "keywords": ["m1"]},
                {"id": "bridge", "domain": "BRIDGE", "formula": "", "variables": [], "keywords": ["br"]},
                {"id": "micro1", "domain": "MICRO", "formula": "", "variables": [], "keywords": ["mi1"]},
            ],
            "logical_negation_pairs": [],
            "causal_edges": [["macro1", "bridge"], ["bridge", "micro1"]],
            "forbidden_edges": [],
        }
        self.tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(reg, self.tmp, ensure_ascii=False)
        self.tmp.close()
        # Hamilton-ring beállítaná 0->1->2->0 — de itt n=3, így a manuális élek
        # ugyanazok. A 2->0-t (Hamilton zárás) kinullázzuk az egyértelműséghez.
        self.eng = AxiomaticInferenceEngine(
            n_nodes=3, registry_path=self.tmp.name
        )
        self.eng.knowledge_matrix = np.eye(3, dtype=np.float64)
        self.eng.knowledge_matrix[0, 1] = 1.0  # macro -> bridge
        self.eng.knowledge_matrix[1, 2] = 1.0  # bridge -> micro

    def tearDown(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_macro_to_micro_two_steps(self) -> None:
        d = self.eng.calculate_domain_distance("MACRO", "MICRO")
        self.assertEqual(d, 2.0)

    def test_micro_to_macro_unreachable(self) -> None:
        d = self.eng.calculate_domain_distance("MICRO", "MACRO")
        self.assertTrue(math.isinf(d))

    def test_unknown_domain_returns_inf(self) -> None:
        d = self.eng.calculate_domain_distance("MACRO", "DOES_NOT_EXIST")
        self.assertTrue(math.isinf(d))

    def test_self_domain_distance_zero(self) -> None:
        d = self.eng.calculate_domain_distance("MACRO", "MACRO")
        self.assertEqual(d, 0.0)


if __name__ == "__main__":
    unittest.main()
