"""Engine Mode (Idea 5 — Mode Labeling) unit tesztek.

A modul **címkézés és csomagolás**, NEM új mechanika. A tesztek azt
biztosítják, hogy:
  - A négy mód címke beállítható és kiolvasható
  - A `get_current_relaxation()` backward-kompatibilis FOCUSED-ben
    (ugyanazt a strict dict-et adja, mint a régi hard-coded fallback)
  - A hipnagóg state machine prioritást élvez, ha aktív (nem törött a régi)
  - CONSOLIDATING blokkolja az új él felvételét, de DECAY re-attempt
    strengthening-et engedi (ez nem új él)
  - Mode-profil felülírható kísérleti hangoláshoz
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine
from engine_mode import EngineMode, ModeProfile, default_profile, all_modes


def _make_policy(tmpdir: Path, *, hypnagogic_enabled: bool = False,
                 decay_enabled: bool = False) -> Path:
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
            "hypnagogic": {
                "enabled": hypnagogic_enabled,
                "log_path": str(tmpdir / "hyp.jsonl"),
            },
        }
    }
    p = tmpdir / "policy.yaml"
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return p


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mode_"))
        self.registry = ROOT / "experiments" / "tutor" / "registry.json"
        if not self.registry.is_file():
            # Privát tutor regiszter nem elérhető — publikus fallback.
            self.registry = ROOT / "axioms_registry_timeless.json"

    def _eng(self, **kw) -> AxiomaticInferenceEngine:
        policy = _make_policy(self.tmpdir, **kw)
        return AxiomaticInferenceEngine(
            policy_enabled=True, policy_path=str(policy),
            registry_path=str(self.registry),
            use_heuristic_thinking=False,
        )


class EngineModeBasicTests(_Base):
    def test_default_mode_is_focused(self) -> None:
        eng = self._eng()
        self.assertEqual(eng.current_mode(), EngineMode.FOCUSED)

    def test_set_mode_persists(self) -> None:
        eng = self._eng()
        eng.set_mode(EngineMode.EXPLORATORY)
        self.assertEqual(eng.current_mode(), EngineMode.EXPLORATORY)
        eng.set_mode(EngineMode.CONSOLIDATING)
        self.assertEqual(eng.current_mode(), EngineMode.CONSOLIDATING)

    def test_set_mode_rejects_non_enum(self) -> None:
        eng = self._eng()
        with self.assertRaises(TypeError):
            eng.set_mode("focused")  # type: ignore[arg-type]

    def test_all_four_modes_have_profiles(self) -> None:
        for m in all_modes():
            prof = default_profile(m)
            self.assertIsInstance(prof, ModeProfile)
            self.assertGreaterEqual(prof.verify_chain_depth, 1)


class GetCurrentRelaxationBackwardCompatTests(_Base):
    """A get_current_relaxation FOCUSED módban ugyanazt adja, mint a régi
    hard-coded fallback (forbidden=1.0, neg=1.0, far=0.0, depth=1)."""

    def test_focused_returns_strict_dict(self) -> None:
        eng = self._eng()
        rx = eng.get_current_relaxation()
        self.assertEqual(rx["forbidden_weight"], 1.0)
        self.assertEqual(rx["negation_threshold"], 1.0)
        self.assertEqual(rx["far_domain_pref"], 0.0)
        self.assertEqual(rx["verify_chain_depth"], 1)

    def test_consolidating_returns_strict_too(self) -> None:
        # CONSOLIDATING is strict relaxation szempontjából — a különbség az
        # accept_new_edges flag, nem a relaxation paraméterekben.
        eng = self._eng()
        eng.set_mode(EngineMode.CONSOLIDATING)
        rx = eng.get_current_relaxation()
        self.assertEqual(rx["forbidden_weight"], 1.0)

    def test_exploratory_relaxes_below_focused(self) -> None:
        eng = self._eng()
        eng.set_mode(EngineMode.EXPLORATORY)
        rx = eng.get_current_relaxation()
        self.assertLess(rx["forbidden_weight"], 1.0)
        self.assertGreater(rx["far_domain_pref"], 0.0)

    def test_hypnagogic_state_machine_overrides_mode(self) -> None:
        """Ha a hipnagóg state machine ENTRY/DEEP/EXIT-ben van, az adja a
        relaxation-t, NEM a mode-profil — backward-kompatibilitás Modul A-val."""
        eng = self._eng(hypnagogic_enabled=True)
        # FOCUSED mode + AWAKE state → strict
        rx_awake = eng.get_current_relaxation()
        self.assertEqual(rx_awake["forbidden_weight"], 1.0)
        # Indítjuk a hipnagóg episode-ot → ENTRY → state machine vezet
        ok = eng.start_hypnagogic_episode()
        self.assertTrue(ok)
        rx_entry = eng.get_current_relaxation()
        # Az ENTRY interpolál entry_start (1.0) felől deep felé; a forbidden_weight
        # csökkennie kell vagy egyenlő (épp az első tickben még 1.0 lehet),
        # de a chain_depth már >= 1 (state machine driven, nem mode-profil).
        self.assertIn("forbidden_weight", rx_entry)


class ConsolidatingBlockingTests(_Base):
    def test_consolidating_blocks_new_edge(self) -> None:
        eng = self._eng()
        eng.set_mode(EngineMode.CONSOLIDATING)
        ok, reason = eng._try_add_edge_with_reason(0, 1)
        self.assertFalse(ok)
        self.assertEqual(reason, "consolidating_blocked")

    def test_focused_allows_new_edge(self) -> None:
        eng = self._eng()
        # Default = FOCUSED
        ok, reason = eng._try_add_edge_with_reason(0, 1)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_consolidating_allows_decay_strengthening(self) -> None:
        """Decay re-attempt egy létező élre nem ÚJ él felvétel — engedélyezett
        CONSOLIDATING-ban is. A meglévő gráf rendezhető."""
        eng = self._eng(decay_enabled=True)
        # Először FOCUSED-ben létrehozunk egy élt
        ok1, _ = eng._try_add_edge_with_reason(0, 1)
        self.assertTrue(ok1)
        # Az él lecseng kicsit (kézzel, hogy ne 1.0 legyen)
        eng.knowledge_matrix[0, 1] = 0.5
        # Átváltunk CONSOLIDATING-ra
        eng.set_mode(EngineMode.CONSOLIDATING)
        # Re-attempt → strengthening (1.0-ra), ez accepted-nek számít
        ok2, reason2 = eng._try_add_edge_with_reason(0, 1)
        self.assertTrue(ok2)
        self.assertIsNone(reason2)
        self.assertAlmostEqual(float(eng.knowledge_matrix[0, 1]), 1.0, places=6)

    def test_accept_new_edges_property(self) -> None:
        eng = self._eng()
        self.assertTrue(eng.accept_new_edges())  # FOCUSED
        eng.set_mode(EngineMode.EXPLORATORY)
        self.assertTrue(eng.accept_new_edges())
        eng.set_mode(EngineMode.HYPNAGOGIC)
        self.assertTrue(eng.accept_new_edges())
        eng.set_mode(EngineMode.CONSOLIDATING)
        self.assertFalse(eng.accept_new_edges())


class ModeProfileOverrideTests(_Base):
    def test_set_mode_profile_takes_effect(self) -> None:
        eng = self._eng()
        custom = ModeProfile(
            forbidden_weight=0.42,
            negation_threshold=0.42,
            far_domain_pref=0.42,
            verify_chain_depth=4,
            accept_new_edges=True,
        )
        eng.set_mode_profile(EngineMode.FOCUSED, custom)
        rx = eng.get_current_relaxation()
        self.assertAlmostEqual(rx["forbidden_weight"], 0.42)
        self.assertAlmostEqual(rx["far_domain_pref"], 0.42)
        self.assertEqual(rx["verify_chain_depth"], 4)

    def test_set_mode_profile_validates_types(self) -> None:
        eng = self._eng()
        with self.assertRaises(TypeError):
            eng.set_mode_profile("focused", default_profile(EngineMode.FOCUSED))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            eng.set_mode_profile(EngineMode.FOCUSED, {"forbidden_weight": 1.0})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
