"""
HypnagogicStateMachine + HypnagogicPolicy tesztek.

Lefedés:
  - kezdeti fázis és start_entry feltételek
  - ENTRY → DEEP → EXIT → COOLDOWN → AWAKE progresszió
  - fisher_trigger DEEP-ből azonnali EXIT
  - fisher_trigger nem-DEEP fázisokban ignorált
  - current_relaxation strict / deep / interpoláció
  - reset
  - YAML backwards compat (hypnagogic mező nélkül)
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hypnagogic_state import HypnagogicPhase, HypnagogicStateMachine
from policy_manager import HypnagogicPolicy, PolicyManager


def _make_policy(**overrides) -> HypnagogicPolicy:
    """Kis lépésszámokkal teszt-policy, hogy a tesztek gyorsak legyenek."""
    base = dict(
        enabled=True,
        entry_steps=4,
        deep_steps=6,
        exit_steps=4,
        cooldown_steps=5,
        forbidden_weight_deep=0.3,
        forbidden_weight_entry_start=1.0,
        negation_threshold_deep=0.5,
        far_domain_pref_deep=0.6,
        verify_chain_depth_deep=3,
    )
    base.update(overrides)
    return HypnagogicPolicy(**base)


class InitialStateTests(unittest.TestCase):
    def test_initial_phase_is_awake(self) -> None:
        """Frissen létrehozott állapotgép AWAKE fázisban indul."""
        sm = HypnagogicStateMachine(_make_policy())
        self.assertIs(sm.current_phase(), HypnagogicPhase.AWAKE)


class StartEntryTests(unittest.TestCase):
    def test_start_entry_from_awake_returns_true(self) -> None:
        """AWAKE-ből start_entry True-t ad és ENTRY-be lép."""
        sm = HypnagogicStateMachine(_make_policy())
        self.assertTrue(sm.start_entry())
        self.assertIs(sm.current_phase(), HypnagogicPhase.ENTRY)

    def test_start_entry_from_other_phases_returns_false(self) -> None:
        """ENTRY/DEEP/EXIT/COOLDOWN fázisokból start_entry False-t ad
        és nem vált fázist."""
        sm = HypnagogicStateMachine(_make_policy())
        sm.start_entry()  # AWAKE → ENTRY
        self.assertFalse(sm.start_entry())
        self.assertIs(sm.current_phase(), HypnagogicPhase.ENTRY)
        # Léptetés DEEP-be
        for _ in range(4):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.DEEP)
        self.assertFalse(sm.start_entry())
        # EXIT-be
        for _ in range(6):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.EXIT)
        self.assertFalse(sm.start_entry())
        # COOLDOWN-ba
        for _ in range(4):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.COOLDOWN)
        self.assertFalse(sm.start_entry())


class PhaseProgressionTests(unittest.TestCase):
    def test_full_cycle_progression(self) -> None:
        """AWAKE → ENTRY → DEEP → EXIT → COOLDOWN → AWAKE a megadott
        lépésszámokkal."""
        policy = _make_policy(
            entry_steps=4, deep_steps=6, exit_steps=4, cooldown_steps=5
        )
        sm = HypnagogicStateMachine(policy)
        self.assertTrue(sm.start_entry())
        # ENTRY: entry_steps tick után DEEP
        for _ in range(3):
            self.assertIs(sm.tick(), HypnagogicPhase.ENTRY)
        self.assertIs(sm.tick(), HypnagogicPhase.DEEP)
        # DEEP: deep_steps tick után EXIT
        for _ in range(5):
            self.assertIs(sm.tick(), HypnagogicPhase.DEEP)
        self.assertIs(sm.tick(), HypnagogicPhase.EXIT)
        # EXIT: exit_steps tick után COOLDOWN
        for _ in range(3):
            self.assertIs(sm.tick(), HypnagogicPhase.EXIT)
        self.assertIs(sm.tick(), HypnagogicPhase.COOLDOWN)
        # COOLDOWN: cooldown_steps tick után AWAKE
        for _ in range(4):
            self.assertIs(sm.tick(), HypnagogicPhase.COOLDOWN)
        self.assertIs(sm.tick(), HypnagogicPhase.AWAKE)


class FisherTriggerTests(unittest.TestCase):
    def test_fisher_trigger_in_deep_causes_immediate_exit(self) -> None:
        """DEEP fázisban fisher_trigger=True azonnal EXIT-be vált
        (függetlenül a számlálótól)."""
        sm = HypnagogicStateMachine(_make_policy())
        sm.start_entry()
        for _ in range(4):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.DEEP)
        # Csak 1 tick DEEP-ben, majd trigger
        sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.DEEP)
        self.assertIs(sm.tick(fisher_trigger=True), HypnagogicPhase.EXIT)

    def test_fisher_trigger_ignored_outside_deep(self) -> None:
        """ENTRY/EXIT/COOLDOWN/AWAKE fázisokban fisher_trigger nem okoz
        korai váltást."""
        sm = HypnagogicStateMachine(_make_policy())
        # AWAKE
        self.assertIs(sm.tick(fisher_trigger=True), HypnagogicPhase.AWAKE)
        sm.start_entry()
        # ENTRY: trigger nem okoz korai DEEP/EXIT-et
        for _ in range(3):
            self.assertIs(
                sm.tick(fisher_trigger=True), HypnagogicPhase.ENTRY
            )
        # 4. tick már a normál DEEP transition
        self.assertIs(sm.tick(fisher_trigger=True), HypnagogicPhase.DEEP)
        # DEEP-be most lép — most a trigger AKTÍV; az "outside DEEP" tesztje
        # itt eltér: léptessünk át EXIT-re normál módon
        for _ in range(6):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.EXIT)
        # EXIT: trigger nem rövidít
        for _ in range(3):
            self.assertIs(
                sm.tick(fisher_trigger=True), HypnagogicPhase.EXIT
            )
        self.assertIs(sm.tick(fisher_trigger=True), HypnagogicPhase.COOLDOWN)
        # COOLDOWN: trigger nem ugratja AWAKE-be előbb
        for _ in range(4):
            self.assertIs(
                sm.tick(fisher_trigger=True), HypnagogicPhase.COOLDOWN
            )
        self.assertIs(sm.tick(fisher_trigger=True), HypnagogicPhase.AWAKE)


class CurrentRelaxationTests(unittest.TestCase):
    def test_strict_values_in_awake(self) -> None:
        """AWAKE-ban strict (alap) értékek."""
        sm = HypnagogicStateMachine(_make_policy())
        rx = sm.current_relaxation()
        self.assertEqual(rx["forbidden_weight"], 1.0)
        self.assertEqual(rx["negation_threshold"], 1.0)
        self.assertEqual(rx["far_domain_pref"], 0.0)
        self.assertEqual(rx["verify_chain_depth"], 1)

    def test_strict_values_in_cooldown(self) -> None:
        """COOLDOWN fázisban szintén strict értékek."""
        sm = HypnagogicStateMachine(_make_policy())
        sm.start_entry()
        # ENTRY (4) + DEEP (6) + EXIT (4) = 14 tick → COOLDOWN
        for _ in range(14):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.COOLDOWN)
        rx = sm.current_relaxation()
        self.assertEqual(rx["forbidden_weight"], 1.0)
        self.assertEqual(rx["negation_threshold"], 1.0)
        self.assertEqual(rx["far_domain_pref"], 0.0)
        self.assertEqual(rx["verify_chain_depth"], 1)

    def test_deep_values_in_middle_of_deep(self) -> None:
        """DEEP fázis közepén pontosan a policy deep értékei."""
        sm = HypnagogicStateMachine(_make_policy())
        sm.start_entry()
        for _ in range(4):
            sm.tick()  # → DEEP
        # Néhány tick DEEP-ben
        for _ in range(3):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.DEEP)
        rx = sm.current_relaxation()
        self.assertAlmostEqual(rx["forbidden_weight"], 0.3)
        self.assertAlmostEqual(rx["negation_threshold"], 0.5)
        self.assertAlmostEqual(rx["far_domain_pref"], 0.6)
        self.assertEqual(rx["verify_chain_depth"], 3)

    def test_interpolated_in_entry_middle(self) -> None:
        """ENTRY közepén az értékek strict és deep közöttiek."""
        sm = HypnagogicStateMachine(_make_policy(entry_steps=4))
        sm.start_entry()
        sm.tick()  # counter=1
        sm.tick()  # counter=2 → 2/4 = 0.5
        rx = sm.current_relaxation()
        # forbidden_weight: lerp(1.0, 0.3, 0.5) = 0.65
        self.assertAlmostEqual(rx["forbidden_weight"], 0.65)
        # negation_threshold: lerp(1.0, 0.5, 0.5) = 0.75
        self.assertAlmostEqual(rx["negation_threshold"], 0.75)
        # far_domain_pref: lerp(0.0, 0.6, 0.5) = 0.3
        self.assertAlmostEqual(rx["far_domain_pref"], 0.3)
        # Az érték strict (1.0) és deep (0.3) között szigorúan
        self.assertGreater(rx["forbidden_weight"], 0.3)
        self.assertLess(rx["forbidden_weight"], 1.0)

    def test_interpolated_in_exit_middle(self) -> None:
        """EXIT közepén az értékek deep és strict közöttiek."""
        policy = _make_policy(entry_steps=4, deep_steps=6, exit_steps=4)
        sm = HypnagogicStateMachine(policy)
        sm.start_entry()
        for _ in range(4):
            sm.tick()  # → DEEP
        for _ in range(6):
            sm.tick()  # → EXIT
        self.assertIs(sm.current_phase(), HypnagogicPhase.EXIT)
        sm.tick()  # counter=1
        sm.tick()  # counter=2 → 2/4 = 0.5
        rx = sm.current_relaxation()
        # forbidden_weight: lerp(0.3, 1.0, 0.5) = 0.65
        self.assertAlmostEqual(rx["forbidden_weight"], 0.65)
        # negation_threshold: lerp(0.5, 1.0, 0.5) = 0.75
        self.assertAlmostEqual(rx["negation_threshold"], 0.75)
        # far_domain_pref: lerp(0.6, 0.0, 0.5) = 0.3
        self.assertAlmostEqual(rx["far_domain_pref"], 0.3)
        self.assertGreater(rx["forbidden_weight"], 0.3)
        self.assertLess(rx["forbidden_weight"], 1.0)


class ResetTests(unittest.TestCase):
    def test_reset_from_any_phase_returns_to_awake(self) -> None:
        """A reset() bármelyik fázisból AWAKE-be visz."""
        sm = HypnagogicStateMachine(_make_policy())
        sm.start_entry()
        sm.tick()
        sm.tick()
        sm.reset()
        self.assertIs(sm.current_phase(), HypnagogicPhase.AWAKE)
        # Reset után lehet újra start_entry
        self.assertTrue(sm.start_entry())
        # DEEP-ből reset
        for _ in range(4):
            sm.tick()
        self.assertIs(sm.current_phase(), HypnagogicPhase.DEEP)
        sm.reset()
        self.assertIs(sm.current_phase(), HypnagogicPhase.AWAKE)


class BackwardsCompatTests(unittest.TestCase):
    def test_yaml_without_hypnagogic_key(self) -> None:
        """A 'hypnagogic' kulcs nélküli YAML is parsolódik; HypnagogicPolicy
        alapértelmezetten enabled=False."""
        yaml_text = (
            "discovery:\n"
            "  enabled: true\n"
            "  log_path: foo.log\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "policy.yaml"
            p.write_text(yaml_text, encoding="utf-8")
            mgr = PolicyManager(p)
            mgr.load()
            hp = mgr.hypnagogic_policy()
            self.assertIsInstance(hp, HypnagogicPolicy)
            self.assertFalse(hp.enabled)
            # alapértelmezett mezők
            self.assertEqual(hp.entry_steps, 8)
            self.assertEqual(hp.deep_steps, 35)
            self.assertEqual(hp.exit_steps, 8)


if __name__ == "__main__":
    unittest.main()
