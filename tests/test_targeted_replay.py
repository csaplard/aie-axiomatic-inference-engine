"""targeted_replay() (Modul MF) unit tesztek."""

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
            "decay_enabled": False,
            "hypnagogic": {"enabled": False},
        }
    }
    p = tmpdir / "policy.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return p


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mf_"))
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


class TargetedReplayTests(_Base):
    def test_empty_targets_returns_zero(self) -> None:
        eng = self._eng()
        self.assertEqual(eng.targeted_replay([], max_reinforce=5), 0)

    def test_max_reinforce_zero_no_op(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.5
        n = eng.targeted_replay([(0, 1)], max_reinforce=0)
        self.assertEqual(n, 0)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 0.5, places=6)

    def test_reinforces_existing_decayed_edge(self) -> None:
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.3  # decayed
        n = eng.targeted_replay([(0, 1)], max_reinforce=5)
        self.assertEqual(n, 1)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 1.0)

    def test_reinforces_path_edges(self) -> None:
        """Ha (0,2) target nincs direkt él, de van 0→1→2 path, az
        összes path-él reinforce-olódik."""
        eng = self._eng()
        eng.knowledge_matrix[0, 1] = 0.4
        eng.knowledge_matrix[1, 2] = 0.5
        # (0,2) nem direkt él, de path létezik
        n = eng.targeted_replay([(0, 2)], max_reinforce=5)
        self.assertEqual(n, 2)  # 2 path-él
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 1.0)
        self.assertEqual(float(eng.knowledge_matrix[1, 2]), 1.0)

    def test_skips_target_when_no_path(self) -> None:
        eng = self._eng()
        # (0, 3) nem ér el sehol
        n = eng.targeted_replay([(0, 3)], max_reinforce=5)
        self.assertEqual(n, 0)

    def test_max_reinforce_caps_total(self) -> None:
        """Ha sok target van, max_reinforce lekorlátozza az összes-erősítést."""
        eng = self._eng()
        # 5 (i,j) direkt él, mind decayed
        for j in range(1, 6):
            eng.knowledge_matrix[0, j] = 0.5
        targets = [(0, j) for j in range(1, 6)]
        n = eng.targeted_replay(targets, max_reinforce=3)
        self.assertEqual(n, 3)
        # 3 él lett 1.0, 2 érintetlen
        n_reinforced = int((eng.knowledge_matrix[0, 1:6] == 1.0).sum())
        self.assertEqual(n_reinforced, 3)

    def test_invalid_indices_skipped(self) -> None:
        eng = self._eng()
        n = eng.targeted_replay([(-1, 0), (0, 999), (0, 0)], max_reinforce=5)
        self.assertEqual(n, 0)

    def test_does_not_create_new_edge_when_no_path(self) -> None:
        """Mastery-feedback NEM hoz létre semmilyen új él-t — csak meglévőket erősít."""
        eng = self._eng()
        # Üres gráf, target (0, 1) — nincs path
        n = eng.targeted_replay([(0, 1)], max_reinforce=5)
        self.assertEqual(n, 0)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 0.0)


if __name__ == "__main__":
    unittest.main()
