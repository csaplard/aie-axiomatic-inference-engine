"""
priority_weight tesztek:
- AxiomRegistry parsing (default 0.5, clamping, hibás érték)
- engine súlyozott sampling: minden seedből priority-arányos választás
- topological_depth_partition kvantilis-alapú működése
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine
from axiom_registry import AxiomRegistry
from graph_metrics import topological_depth_partition


def _write_registry(nodes_with_priority: list, tmp_dir: Path) -> Path:
    data = {
        "version": "test",
        "nodes": [
            {
                "id": f"n{i}",
                "domain": "LOGIC",
                "formula": "",
                "variables": [],
                "keywords": [f"n{i}"],
                **(
                    {"priority_weight": p} if p is not None else {}
                ),
            }
            for i, p in enumerate(nodes_with_priority)
        ],
        "logical_negation_pairs": [],
        "causal_edges": [],
        "forbidden_edges": [],
    }
    p = tmp_dir / "reg.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class PriorityRegistryTests(unittest.TestCase):
    def test_default_priority_is_0_5(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _write_registry([None, None, None], Path(d))
            reg = AxiomRegistry(path)
            self.assertEqual(reg.priority_array(), [0.5, 0.5, 0.5])

    def test_explicit_priority_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _write_registry([0.1, 0.9, 0.5], Path(d))
            reg = AxiomRegistry(path)
            self.assertEqual(reg.priority_array(), [0.1, 0.9, 0.5])

    def test_priority_clamped_to_unit_interval(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = _write_registry([-0.3, 1.5, 0.4], Path(d))
            reg = AxiomRegistry(path)
            self.assertEqual(reg.priority_array(), [0.0, 1.0, 0.4])

    def test_invalid_priority_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            data = {
                "version": "test",
                "nodes": [
                    {
                        "id": "n0", "domain": "LOGIC", "formula": "",
                        "variables": [], "keywords": ["n0"],
                        "priority_weight": "not_a_number",
                    },
                ],
                "logical_negation_pairs": [],
                "causal_edges": [],
                "forbidden_edges": [],
            }
            p = Path(d) / "reg.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            reg = AxiomRegistry(p)
            self.assertEqual(reg.priority_array(), [0.5])


class WeightedSamplingTests(unittest.TestCase):
    """Empirikus teszt: 1000 random_pair lépésen át a magas-priority csúcs
    szignifikánsan többször jelenik meg, mint az alacsony."""

    def test_high_priority_sampled_more_often(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            # 4 csúcs: 2 high (priority 0.9), 2 low (priority 0.1)
            path = _write_registry([0.9, 0.1, 0.9, 0.1], Path(d))
            eng = AxiomaticInferenceEngine(
                n_nodes=4, registry_path=str(path),
                use_heuristic_thinking=False,  # random_pair mode
            )
            # Tiszta gráf: minden sornak van legalább 1 él (Hamilton-ring)
            np.random.seed(123)
            counter: Counter = Counter()
            for _ in range(1000):
                # Csak a sampling részt teszteljük: weighted_pair_choice
                nonzero = np.where(eng.knowledge_matrix.sum(axis=1) > 0)[0]
                pair = eng._weighted_pair_choice(nonzero)
                if pair is None:
                    continue
                for x in pair:
                    counter[int(x)] += 1
            high_total = counter[0] + counter[2]
            low_total = counter[1] + counter[3]
            # Várt arány ~9:1, gyakorlatban legalább 2x
            self.assertGreater(high_total, low_total * 2)


class PartitionMetricTests(unittest.TestCase):
    def test_partition_with_clear_high_low_groups(self) -> None:
        # 6 csúcs, lánc 0->1->2->3->4->5
        n = 6
        A = np.eye(n, dtype=np.float64)
        for i in range(n - 1):
            A[i, i + 1] = 1.0
        # priority: első 2 high (0.9), utolsó 2 low (0.1), közepe 0.5
        pri = np.array([0.9, 0.9, 0.5, 0.5, 0.1, 0.1], dtype=np.float64)
        topo_h, topo_l, ratio = topological_depth_partition(A, pri)
        # high partíció = csúcsok 0, 1 (2 csúcs, lánc 0->1) → topo=2
        # low partíció = csúcsok 4, 5 (2 csúcs, lánc 4->5) → topo=2
        self.assertEqual(topo_h, 2)
        self.assertEqual(topo_l, 2)
        self.assertAlmostEqual(ratio, 1.0)

    def test_partition_concentrated_in_high(self) -> None:
        # Lánc 0->1->2->3, priority csak az első 3-on magas
        n = 4
        A = np.eye(n, dtype=np.float64)
        A[0, 1] = A[1, 2] = A[2, 3] = 1.0
        pri = np.array([0.9, 0.9, 0.9, 0.1], dtype=np.float64)
        topo_h, topo_l, ratio = topological_depth_partition(A, pri)
        self.assertGreaterEqual(topo_h, 2)
        self.assertEqual(topo_l, 1)
        self.assertGreater(ratio, 1.0)

    def test_partition_empty_matrix(self) -> None:
        A = np.zeros((0, 0))
        pri = np.array([], dtype=np.float64)
        topo_h, topo_l, ratio = topological_depth_partition(A, pri)
        self.assertEqual(topo_h, 0)
        self.assertEqual(topo_l, 0)


if __name__ == "__main__":
    unittest.main()
