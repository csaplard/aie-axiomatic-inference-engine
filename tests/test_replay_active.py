"""replay_active() (Modul H replay-edge) unit tesztek."""

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


def _make_policy(tmpdir: Path, decay_enabled: bool = True) -> Path:
    data = {
        "discovery": {
            "enabled": True, "daemon_mode": False, "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False, "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "log_path": str(tmpdir / "disc.log"),
            "telemetry_log_path": str(tmpdir / "tel.log"),
            "random_seed": 42,
            "max_runtime_seconds": 0,
            "decay_enabled": decay_enabled,
            "decay_factor": 0.9,
            "decay_threshold": 0.05,
            "hypnagogic": {"enabled": False},
        }
    }
    p = tmpdir / "policy.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return p


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="replay_"))
        self.registry = ROOT / "experiments" / "tutor" / "registry.json"
        if not self.registry.is_file():
            # Privát tutor regiszter nem elérhető — publikus fallback.
            self.registry = ROOT / "axioms_registry_timeless.json"

    def _eng(self) -> AxiomaticInferenceEngine:
        return AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(_make_policy(self.tmpdir)),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )


class ReplayActiveTests(_Base):
    def test_no_candidates_returns_zero(self) -> None:
        eng = self._eng()
        # Csak diagonális → nincs jelölt
        self.assertEqual(eng.replay_active(k=5), 0)

    def test_strengthens_weak_edge(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.3
        n = eng.replay_active(k=1)
        self.assertEqual(n, 1)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 1.0)

    def test_does_not_pick_below_lower(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.02  # alatta a lower=0.05-nek
        n = eng.replay_active(k=5, lower=0.05)
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 0.02, places=6)

    def test_does_not_pick_at_one(self) -> None:
        """A 1.0-ás éleket nem választja (azok már strong)."""
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 1.0
        n = eng.replay_active(k=5)
        self.assertEqual(n, 0)

    def test_picks_at_most_k(self) -> None:
        eng = self._eng()
        # 10 db gyenge él
        for j in range(1, 11):
            eng.knowledge_matrix[0, j] = 0.3
        n = eng.replay_active(k=3)
        self.assertEqual(n, 3)
        # 3 db visszaerősítve, 7 érintetlen
        n_strong = int((eng.knowledge_matrix[0, 1:11] == 1.0).sum())
        n_weak = int(np.isclose(eng.knowledge_matrix[0, 1:11], 0.3).sum())
        self.assertEqual(n_strong, 3)
        self.assertEqual(n_weak, 7)

    def test_picks_all_when_fewer_candidates(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.3
        eng.knowledge_matrix[0, 2] = 0.5
        n = eng.replay_active(k=10)
        self.assertEqual(n, 2)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 1.0)
        self.assertEqual(float(eng.knowledge_matrix[0, 2]), 1.0)

    def test_does_not_touch_diagonal(self) -> None:
        eng = self._eng()
        # A diagonális 1.0 marad még akkor is, ha a jelöltek között lenne
        eng.knowledge_matrix[0, 1] = 0.3
        eng.replay_active(k=5)
        for i in range(eng.n_nodes):
            self.assertEqual(float(eng.knowledge_matrix[i, i]), 1.0)

    def test_k_zero_no_op(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.3
        n = eng.replay_active(k=0)
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 0.3, places=6)


if __name__ == "__main__":
    unittest.main()
