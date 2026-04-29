"""
verify_logic tesztek: tranzitív záró lépés (i→k és k→j) ⇒ i→j igaz.

A kernel verify_logic NEM teljes tranzitív zárás — csak EGY köztes lépést keres.
A teszt ehhez igazodik (és dokumentálja is ezt a viselkedést).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine


def _bare_engine(n: int) -> AxiomaticInferenceEngine:
    """Üres regiszter nélküli, n_nodes méretű, csak identitás-mátrix kezdettel."""
    eng = AxiomaticInferenceEngine(n_nodes=n, use_axiom_registry=False)
    eng.knowledge_matrix = np.eye(n, dtype=np.float64)
    return eng


class VerifyLogicTests(unittest.TestCase):
    def test_one_hop_transitivity_holds(self) -> None:
        eng = _bare_engine(4)
        eng.knowledge_matrix[0, 1] = 1.0  # 0 -> 1
        eng.knowledge_matrix[1, 2] = 1.0  # 1 -> 2
        # 0 -> 2 igazolható tranzitíven (k=1)
        self.assertTrue(eng.verify_logic(0, 2))

    def test_no_intermediate_returns_false(self) -> None:
        eng = _bare_engine(4)
        eng.knowledge_matrix[0, 1] = 1.0
        # Nincs olyan k, ahol 0→k és k→2
        self.assertFalse(eng.verify_logic(0, 2))

    def test_self_pair_is_false(self) -> None:
        """i==j: nem deduktív lépés (kernel docstring szerint sem)."""
        eng = _bare_engine(3)
        self.assertFalse(eng.verify_logic(1, 1))

    def test_two_hop_chain_NOT_proved_in_one_step(self) -> None:
        """
        Dokumentálja: verify_logic CSAK 1 köztes lépést néz.
        0->1, 1->2, 2->3 → 0->3 NEM igazolható egy lépésben (kell deductive_saturate).
        """
        eng = _bare_engine(5)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        eng.knowledge_matrix[2, 3] = 1.0
        self.assertFalse(eng.verify_logic(0, 3))

    def test_reverse_direction_not_implied(self) -> None:
        """0→1, 1→2 nem implikálja 2→0-t (irányított)."""
        eng = _bare_engine(4)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        self.assertFalse(eng.verify_logic(2, 0))


class DeductiveSaturateTests(unittest.TestCase):
    def test_saturate_closes_two_hop_chain(self) -> None:
        eng = _bare_engine(5)
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        eng.knowledge_matrix[2, 3] = 1.0
        eng.deductive_saturate()
        # Tranzitív zárás után 0→2, 0→3, 1→3 mind él.
        self.assertGreater(eng.knowledge_matrix[0, 2], 0)
        self.assertGreater(eng.knowledge_matrix[0, 3], 0)
        self.assertGreater(eng.knowledge_matrix[1, 3], 0)


if __name__ == "__main__":
    unittest.main()
