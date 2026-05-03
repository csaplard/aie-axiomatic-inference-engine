"""Decay (Modul B+DECAY) unit tesztek."""

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


def _make_policy(tmpdir: Path, decay_enabled: bool = True,
                 decay_factor: float = 0.9, decay_threshold: float = 0.05) -> Path:
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
            "decay_factor": decay_factor,
            "decay_threshold": decay_threshold,
            "hypnagogic": {"enabled": False},
        }
    }
    p = tmpdir / "policy.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return p


class DecayMechanicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="decay_"))
        self.registry = ROOT / "experiments" / "tutor" / "registry.json"
        if not self.registry.is_file():
            # Privát tutor regiszter nem elérhető — publikus fallback.
            self.registry = ROOT / "axioms_registry_timeless.json"

    def test_decay_disabled_keeps_edges(self) -> None:
        """decay_enabled=False → matrix nem változik think_step után (csak az új él)."""
        policy = _make_policy(self.tmpdir, decay_enabled=False)
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        eng._try_add_edge_with_reason(0, 1)
        v_before = float(eng.knowledge_matrix[0, 1])
        eng._finalize_think_step(0.0)
        v_after = float(eng.knowledge_matrix[0, 1])
        self.assertEqual(v_before, v_after)
        self.assertEqual(v_after, 1.0)

    def test_decay_enabled_reduces_edges(self) -> None:
        """decay_enabled=True → matrix off-diag elemei csökkennek."""
        policy = _make_policy(self.tmpdir, decay_enabled=True, decay_factor=0.9)
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        eng._try_add_edge_with_reason(0, 1)
        eng._finalize_think_step(0.0)
        # matrix[0,1] = 1.0 → 0.9 (egy decay step után)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 0.9, places=6)

    def test_decay_diagonal_preserved(self) -> None:
        """A diagonális 1.0 marad decay után."""
        policy = _make_policy(self.tmpdir, decay_enabled=True, decay_factor=0.5)
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        for _ in range(20):
            eng._finalize_think_step(0.0)
        # Diagonális minden elem 1.0
        for i in range(eng.n_nodes):
            self.assertEqual(float(eng.knowledge_matrix[i, i]), 1.0)

    def test_decay_threshold_removes_edge(self) -> None:
        """Az él, amelyik a decay_threshold alá süllyed, 0.0-ra törlődik."""
        policy = _make_policy(
            self.tmpdir, decay_enabled=True,
            decay_factor=0.5, decay_threshold=0.1,
        )
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        eng._try_add_edge_with_reason(0, 1)
        # 1.0 → 0.5 → 0.25 → 0.125 → 0.0625 < 0.1 → törlődik
        for _ in range(4):
            eng._finalize_think_step(0.0)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 0.0)

    def test_re_attempt_strengthens_in_decay_mode(self) -> None:
        """Decay-módban egy létező él re-attempt-je strengthening (1.0-ra állítás)."""
        policy = _make_policy(self.tmpdir, decay_enabled=True, decay_factor=0.5)
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        eng._try_add_edge_with_reason(0, 1)
        eng._finalize_think_step(0.0)
        # 1.0 → 0.5
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 0.5, places=6)
        # Re-attempt → strengthening
        added, reason = eng._try_add_edge_with_reason(0, 1)
        self.assertTrue(added)
        self.assertIsNone(reason)
        self.assertEqual(float(eng.knowledge_matrix[0, 1]), 1.0)

    def test_re_attempt_rejects_in_non_decay_mode(self) -> None:
        """Decay nélkül a re-attempt 'exists' rejekt-tel végződik."""
        policy = _make_policy(self.tmpdir, decay_enabled=False)
        eng = AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )
        eng._try_add_edge_with_reason(0, 1)
        added, reason = eng._try_add_edge_with_reason(0, 1)
        self.assertFalse(added)
        self.assertEqual(reason, "exists")


if __name__ == "__main__":
    unittest.main()
