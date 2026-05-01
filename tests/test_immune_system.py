"""
Immunrendszer tesztek: forbidden_edges és _would_contradict_edge működése,
+ _try_add_edge_with_reason elutasítási okok ('forbidden', 'contradiction', 'exists').

Mini regiszter JSON-on tesztelünk, hogy a regiszter-betöltés és a negáció-leképezés
is be legyen járva.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine


def _mini_registry() -> dict:
    return {
        "version": "test-1.0",
        "nodes": [
            {"id": "A", "domain": "LOGIC", "formula": "", "variables": [], "keywords": ["a"]},
            {"id": "B", "domain": "LOGIC", "formula": "", "variables": [], "keywords": ["b"]},
            {"id": "notA", "domain": "LOGIC", "formula": "", "variables": [], "keywords": ["nota"]},
            {"id": "C", "domain": "LOGIC", "formula": "", "variables": [], "keywords": ["c"]},
        ],
        "logical_negation_pairs": [["A", "notA"]],
        "causal_edges": [["A", "B"]],
        "forbidden_edges": [["B", "A"]],
    }


class ImmuneSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(_mini_registry(), self.tmp, ensure_ascii=False)
        self.tmp.close()
        self.eng = AxiomaticInferenceEngine(
            n_nodes=4, registry_path=self.tmp.name
        )
        # Hamilton-gyűrű kikapcsolása teszt-determinizmushoz: tiszta mátrix +
        # csak a regiszter explicit causal_edges élei.
        self.eng.knowledge_matrix = np.eye(4, dtype=np.float64)
        self.eng.knowledge_matrix[0, 1] = 1.0  # A -> B (causal_edges)

    def tearDown(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_forbidden_edge_detected(self) -> None:
        # B->A explicit tilos
        self.assertTrue(self.eng.is_edge_forbidden(1, 0))
        # A->B nem tilos
        self.assertFalse(self.eng.is_edge_forbidden(0, 1))

    def test_try_add_returns_forbidden(self) -> None:
        # Üres mátrix kívülről írva: kényszerítsük az állapotot, hogy NE legyen út
        # Csak forbidden ellenőrzést teszteljük: B->A
        added, reject = self.eng._try_add_edge_with_reason(1, 0)
        self.assertFalse(added)
        self.assertEqual(reject, "forbidden")

    def test_try_add_returns_exists(self) -> None:
        # A->B causal_edges miatt _seed_axioms beállította
        self.assertGreater(self.eng.knowledge_matrix[0, 1], 0.0)
        added, reject = self.eng._try_add_edge_with_reason(0, 1)
        self.assertFalse(added)
        self.assertEqual(reject, "exists")

    def test_contradiction_detected_via_negation_path(self) -> None:
        """
        A és notA negációs pár. Ha létezik C -> notA út, akkor C -> A felvétele
        ellentmondás (A -> ... -> notA elérhető lenne A-ból, de itt fordítva nézzük:
        a kódban: i->j elvetés, ha i->...->neg(j) létezik).
        Setup: C -> notA él, próbáljunk C -> A élt.
        """
        self.eng.knowledge_matrix[3, 2] = 1.0  # C(idx=3) -> notA(idx=2)
        added, reject = self.eng._try_add_edge_with_reason(3, 0)  # C -> A
        self.assertFalse(added)
        self.assertEqual(reject, "contradiction")

    def test_negation_map_is_symmetric(self) -> None:
        # _build_negation_map szimmetrikussá teszi a párokat (új list-API)
        self.assertIn(2, self.eng._negation.get(0, []))  # A -> notA
        self.assertIn(0, self.eng._negation.get(2, []))  # notA -> A


if __name__ == "__main__":
    unittest.main()
