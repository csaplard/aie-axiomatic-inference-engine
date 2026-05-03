"""generalize_transitive() (Modul H generalization) unit tesztek."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine


def _make_policy(tmpdir: Path) -> Path:
    data = {
        "discovery": {
            "enabled": True, "daemon_mode": False, "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False, "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "log_path": str(tmpdir / "disc.log"),
            "telemetry_log_path": str(tmpdir / "tel.log"),
            "random_seed": 42,
            "max_runtime_seconds": 0,
            "decay_enabled": False,  # decay nem releváns ezen tesztekhez
            "hypnagogic": {"enabled": False},
        }
    }
    p = tmpdir / "policy.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return p


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="gen_"))
        self.registry = ROOT / "experiments" / "tutor" / "registry.json"
        if not self.registry.is_file():
            # Privát tutor regiszter nem elérhető — publikus fallback.
            self.registry = ROOT / "axioms_registry_timeless.json"

    def _eng(self) -> AxiomaticInferenceEngine:
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(_make_policy(self.tmpdir)),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        # Üres gráf: a tesztek konkrét off-diagonális élek kontrollált
        # beállítását feltételezik; a regisztri által betöltött initial
        # causal_edges-eket null-ra állítjuk, csak a diagonálist tartjuk.
        eng.knowledge_matrix[:, :] = 0.0
        np.fill_diagonal(eng.knowledge_matrix, 1.0)
        return eng


class GeneralizeTransitiveTests(_Base):
    def test_no_candidates_returns_zero(self) -> None:
        eng = self._eng()
        # Csak diagonális → nincs strong-strong két-hop
        self.assertEqual(eng.generalize_transitive(theta=0.7, k=5), 0)

    def test_creates_transitive_closure(self) -> None:
        eng = self._eng()
        # A[0,1] = 1.0, A[1,2] = 1.0, A[0,2] = 0 → emerál A[0,2] = 1.0
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        n = eng.generalize_transitive(theta=0.7, k=5)
        self.assertEqual(n, 1)
        self.assertEqual(float(eng.knowledge_matrix[0, 2]), 1.0)

    def test_does_not_pick_below_theta(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.5  # alatta a 0.7-nek
        eng.knowledge_matrix[1, 2] = 1.0
        n = eng.generalize_transitive(theta=0.7, k=5)
        self.assertEqual(n, 0)
        self.assertEqual(float(eng.knowledge_matrix[0, 2]), 0.0)

    def test_does_not_create_when_direct_exists(self) -> None:
        """Ha A[i,k] már nem nulla, NEM emerál új closure-t."""
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        eng.knowledge_matrix[0, 2] = 0.5  # már létezik
        n = eng.generalize_transitive(theta=0.7, k=5)
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 2]), 0.5, places=6)

    def test_picks_at_most_k(self) -> None:
        eng = self._eng()
        # 5 lehetséges closure: (0,2),(0,3),(0,4),(0,5),(0,6)
        eng.knowledge_matrix[0, 1] = 1.0
        for k_target in [2, 3, 4, 5, 6]:
            eng.knowledge_matrix[1, k_target] = 1.0
        n = eng.generalize_transitive(theta=0.7, k=2)
        self.assertEqual(n, 2)
        # 2 új él létrejött a 5 jelölt közül
        n_new = int((eng.knowledge_matrix[0, 2:7] == 1.0).sum())
        self.assertEqual(n_new, 2)

    def test_does_not_touch_diagonal(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 0] = 1.0  # 0→1, 1→0 → 0→0 lenne self-loop
        n = eng.generalize_transitive(theta=0.7, k=5)
        # A diagonális mindig 1.0 marad, és a self-loop "új él"-t nem emeráljuk
        for i in range(eng.n_nodes):
            self.assertEqual(float(eng.knowledge_matrix[i, i]), 1.0)

    def test_k_zero_no_op(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 1.0
        eng.knowledge_matrix[1, 2] = 1.0
        n = eng.generalize_transitive(theta=0.7, k=0)
        self.assertEqual(n, 0)
        self.assertEqual(float(eng.knowledge_matrix[0, 2]), 0.0)


if __name__ == "__main__":
    unittest.main()
