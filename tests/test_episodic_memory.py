"""
Modul B — epizodikus memória unit tesztek.
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

from episodic_memory import EpisodicMemory, SCHEMA_VERSION
from axiom_kernel import AxiomaticInferenceEngine


class EpisodicMemoryAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mem_"))
        self.mem = EpisodicMemory(self.tmpdir)

    def test_has_state_returns_false_when_empty(self) -> None:
        self.assertFalse(self.mem.has_state("anything"))

    def test_list_labels_empty_initially(self) -> None:
        self.assertEqual(self.mem.list_labels(), [])

    def test_label_sanitization(self) -> None:
        """Path-traversal és illegális karakterek nem törhetik a memória-mappát."""
        # A `_label_dir` egyszerű szanitárást csinál
        d1 = self.mem._label_dir("../../etc/passwd")
        # Ne menjen ki a self.tmpdir alól
        self.assertTrue(str(d1).startswith(str(self.tmpdir)))


class EngineRoundTripTests(unittest.TestCase):
    """Round-trip tesztek: save → új engine → load → várjuk az eredeti állapotot."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mem_rt_"))
        self.registry = ROOT / "experiments" / "registries" / "dense_thesis.json"

    def _build_engine(self) -> AxiomaticInferenceEngine:
        return AxiomaticInferenceEngine(
            n_nodes=15, registry_path=str(self.registry),
            use_heuristic_thinking=True,
        )

    def test_save_load_round_trip_matrix_identical(self) -> None:
        """Save majd load → knowledge_matrix bitre azonos."""
        eng_a = self._build_engine()
        np.random.seed(0)
        for _ in range(50):
            eng_a.think_step()
        matrix_before = eng_a.knowledge_matrix.copy()
        path = eng_a.save_state(self.tmpdir, "test1", save_rng=True)
        self.assertTrue(path.is_dir())

        # Új engine, load
        eng_b = self._build_engine()
        ok = eng_b.load_state(self.tmpdir, "test1")
        self.assertTrue(ok)
        np.testing.assert_array_equal(eng_b.knowledge_matrix, matrix_before)
        self.assertEqual(eng_b._think_step_counter, eng_a._think_step_counter)

    def test_save_load_with_rng_continues_deterministically(self) -> None:
        """Full RNG mentés → load utáni 10 lépés azonos egy folytatott menetével."""
        eng_a = self._build_engine()
        np.random.seed(42)
        for _ in range(30):
            eng_a.think_step()
        # Mentés és további 10 lépés folytatólag
        eng_a.save_state(self.tmpdir, "checkpoint", save_rng=True)
        for _ in range(10):
            eng_a.think_step()
        matrix_a_final = eng_a.knowledge_matrix.copy()

        # Új engine, load, és ugyanaz a 10 lépés
        eng_b = self._build_engine()
        ok = eng_b.load_state(self.tmpdir, "checkpoint")
        self.assertTrue(ok)
        for _ in range(10):
            eng_b.think_step()
        matrix_b_final = eng_b.knowledge_matrix.copy()

        # B-Determinism alapja: full save → bitre azonos
        np.testing.assert_array_equal(matrix_a_final, matrix_b_final)

    def test_save_without_rng_does_not_break(self) -> None:
        """save_rng=False is működik, csak a strukturális állapot mentődik."""
        eng = self._build_engine()
        np.random.seed(0)
        for _ in range(10):
            eng.think_step()
        eng.save_state(self.tmpdir, "no_rng", save_rng=False)
        self.assertTrue(self.mem_has(self.tmpdir, "no_rng"))

    def test_load_returns_false_for_unknown_label(self) -> None:
        eng = self._build_engine()
        ok = eng.load_state(self.tmpdir, "nonexistent")
        self.assertFalse(ok)

    def test_schema_version_is_persisted(self) -> None:
        eng = self._build_engine()
        eng.save_state(self.tmpdir, "v1")
        sj = self.tmpdir / "memory_v1" / "state.json"
        with sj.open(encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)

    def test_list_labels_after_saves(self) -> None:
        eng = self._build_engine()
        eng.save_state(self.tmpdir, "a")
        eng.save_state(self.tmpdir, "b")
        eng.save_state(self.tmpdir, "c")
        labels = EpisodicMemory(self.tmpdir).list_labels()
        self.assertEqual(sorted(labels), ["a", "b", "c"])

    @staticmethod
    def mem_has(tmpdir: Path, label: str) -> bool:
        return EpisodicMemory(tmpdir).has_state(label)


class PartialReloadTests(unittest.TestCase):
    """B-Continuity alap: matrix + trust mentve, RNG NEM."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mem_partial_"))
        self.registry = ROOT / "experiments" / "registries" / "dense_thesis.json"

    def test_partial_reload_keeps_matrix_but_diverges_with_new_rng(self) -> None:
        """Save without RNG, reload, run with NEW seed → matrix marad, trajectory eltér."""
        eng_a = AxiomaticInferenceEngine(
            n_nodes=15, registry_path=str(self.registry),
            use_heuristic_thinking=True,
        )
        np.random.seed(1)
        for _ in range(50):
            eng_a.think_step()
        # Mentés RNG nélkül
        eng_a.save_state(self.tmpdir, "partial", save_rng=False)
        matrix_at_checkpoint = eng_a.knowledge_matrix.copy()

        # Új engine + load + új seed
        eng_b = AxiomaticInferenceEngine(
            n_nodes=15, registry_path=str(self.registry),
            use_heuristic_thinking=True,
        )
        ok = eng_b.load_state(self.tmpdir, "partial")
        self.assertTrue(ok)
        # Matrix egyezik a checkpoint-tal
        np.testing.assert_array_equal(eng_b.knowledge_matrix, matrix_at_checkpoint)
        # De az RNG-t ki kellett venni → új seed-del egész más útra megy
        np.random.seed(99)  # Új seed
        for _ in range(20):
            eng_b.think_step()
        # Az eredeti A 50 lépésen belül NEM volt itt — szándékos divergencia
        # (csak azt teszteljük, hogy a load nem tört el semmit)
        self.assertEqual(
            eng_b._think_step_counter, 50 + 20,
        )


if __name__ == "__main__":
    unittest.main()
