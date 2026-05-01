"""
Modul E — predictive_layer unit tesztek.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from predictive_layer import L1RuleSet, GlobalRule, brier_score, _domain_key


class L1RuleSetTests(unittest.TestCase):
    def test_constructor_validation(self) -> None:
        with self.assertRaises(ValueError):
            L1RuleSet(alpha=0.0)
        with self.assertRaises(ValueError):
            L1RuleSet(alpha=1.0)
        with self.assertRaises(ValueError):
            L1RuleSet(init_value=-0.1)

    def test_initial_predict_returns_init_value(self) -> None:
        rs = L1RuleSet(alpha=0.1, init_value=0.5)
        self.assertEqual(rs.predict("LOGIC", "INFO"), 0.5)

    def test_update_moves_toward_actual(self) -> None:
        """3 db accepted update után: 0.5 → 0.5*0.9 + 0.1 = 0.55 → 0.595 → 0.6355"""
        rs = L1RuleSet(alpha=0.1, init_value=0.5)
        rs.update("LOGIC", "INFO", True)
        self.assertAlmostEqual(rs.predict("LOGIC", "INFO"), 0.55)
        rs.update("LOGIC", "INFO", True)
        self.assertAlmostEqual(rs.predict("LOGIC", "INFO"), 0.595)
        rs.update("LOGIC", "INFO", True)
        self.assertAlmostEqual(rs.predict("LOGIC", "INFO"), 0.6355)

    def test_update_returns_delta(self) -> None:
        rs = L1RuleSet(alpha=0.2, init_value=0.5)
        delta = rs.update("LOGIC", "INFO", True)
        # 0.2*1 + 0.8*0.5 = 0.6, delta = 0.1
        self.assertAlmostEqual(delta, 0.1)

    def test_freeze_blocks_update(self) -> None:
        rs = L1RuleSet(alpha=0.1)
        rs.update("LOGIC", "INFO", True)
        rs.freeze()
        before = rs.predict("LOGIC", "INFO")
        delta = rs.update("LOGIC", "INFO", False)
        self.assertIsNone(delta)
        self.assertEqual(rs.predict("LOGIC", "INFO"), before)

    def test_separate_rules_per_pair(self) -> None:
        rs = L1RuleSet(alpha=0.5)
        rs.update("LOGIC", "INFO", True)   # → 0.75
        rs.update("QM", "NEWTON", False)   # → 0.25
        self.assertAlmostEqual(rs.predict("LOGIC", "INFO"), 0.75)
        self.assertAlmostEqual(rs.predict("QM", "NEWTON"), 0.25)

    def test_unfreeze_resumes(self) -> None:
        rs = L1RuleSet(alpha=0.5)
        rs.freeze()
        self.assertIsNone(rs.update("X", "Y", True))
        rs.unfreeze()
        delta = rs.update("X", "Y", True)
        self.assertIsNotNone(delta)

    def test_total_updates_count(self) -> None:
        rs = L1RuleSet(alpha=0.1)
        for _ in range(5):
            rs.update("X", "Y", True)
        for _ in range(3):
            rs.update("A", "B", False)
        self.assertEqual(rs.total_updates(), 8)
        self.assertEqual(rs.update_count("X", "Y"), 5)
        self.assertEqual(rs.update_count("A", "B"), 3)


class GlobalRuleTests(unittest.TestCase):
    def test_predict_irrespective_of_pair(self) -> None:
        gr = GlobalRule(alpha=0.5, init_value=0.7)
        self.assertEqual(gr.predict("LOGIC", "INFO"), 0.7)
        self.assertEqual(gr.predict("QM", "NEWTON"), 0.7)

    def test_update_aggregates_globally(self) -> None:
        gr = GlobalRule(alpha=0.5, init_value=0.5)
        gr.update("LOGIC", "INFO", True)   # 0.5 → 0.75
        gr.update("QM", "NEWTON", False)   # 0.75 → 0.375
        self.assertAlmostEqual(gr.value, 0.375)

    def test_freeze(self) -> None:
        gr = GlobalRule(alpha=0.1)
        gr.freeze()
        delta = gr.update("X", "Y", True)
        self.assertIsNone(delta)


class BrierScoreTests(unittest.TestCase):
    def test_perfect_predictions(self) -> None:
        bs = brier_score([1.0, 0.0, 1.0], [1, 0, 1])
        self.assertEqual(bs, 0.0)

    def test_uniform_random(self) -> None:
        bs = brier_score([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0])
        self.assertEqual(bs, 0.25)

    def test_empty_returns_nan(self) -> None:
        import math
        self.assertTrue(math.isnan(brier_score([], [])))


class DomainKeyTests(unittest.TestCase):
    def test_string_pass(self) -> None:
        self.assertEqual(_domain_key("LOGIC"), "LOGIC")

    def test_none_falls_back(self) -> None:
        self.assertEqual(_domain_key(None), "UNK")

    def test_enum_uses_value(self) -> None:
        from enum import Enum
        class D(str, Enum):
            X = "DOMAIN_X"
        self.assertEqual(_domain_key(D.X), "DOMAIN_X")


class EngineIntegrationTests(unittest.TestCase):
    def test_attach_and_observe(self) -> None:
        from axiom_kernel import AxiomaticInferenceEngine
        registry = ROOT / "experiments" / "registries" / "C2_domain_negation.json"
        eng = AxiomaticInferenceEngine(
            n_nodes=80, registry_path=str(registry),
            use_heuristic_thinking=True,
        )
        rs = L1RuleSet(alpha=0.1)
        gr = GlobalRule(alpha=0.1)
        eng.attach_predictive_layer(l1_rules=rs, global_rule=gr)
        for _ in range(50):
            eng.think_step()
        # A rule-set és global rule frissült
        self.assertGreater(rs.total_updates(), 0)
        self.assertGreater(gr._update_count, 0)


if __name__ == "__main__":
    unittest.main()
