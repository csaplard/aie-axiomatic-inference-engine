"""
Modul A integrációs tesztek — a teljes pipeline (engine + emission_logger +
fisher_realtime + hypnagogic_state) együttes működése.

Nem unit teszt: érdemi end-to-end forgatókönyv, kis seedszámmal és lépésszámmal.
"""

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
from hypnagogic_state import HypnagogicPhase


def _strict_immune_with_hypnagogic(
    log_dir: Path, seed: int = 0, hypnagogic_enabled: bool = True
) -> Path:
    """Policy YAML strict-immune módban + hypnagogic engedélyezve / kikapcsolva."""
    data = {
        "discovery": {
            "enabled": True,
            "daemon_mode": True,
            "seed_hamilton_ring": False,
            "ignore_forbidden_edges": False,
            "ignore_negation_contradictions": False,
            "telemetry_enabled": False,
            "telemetry_log_path": str(log_dir / "tel.log"),
            "log_path": str(log_dir / "disc.log"),
            "random_seed": int(seed),
            "max_runtime_seconds": 0,
            "hypnagogic": {
                "enabled": hypnagogic_enabled,
                "entry_steps": 5,
                "deep_steps": 15,
                "exit_steps": 5,
                "cooldown_steps": 50,
                "forbidden_weight_deep": 0.3,
                "fisher_trigger_factor": 2.0,
                "fisher_min_history": 10,
                "log_path": str(log_dir / "hypnagogic_log.jsonl"),
            },
        }
    }
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(data, tf, allow_unicode=True)
    tf.close()
    return Path(tf.name)


class HypnagogicIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="hyp_int_"))

    def tearDown(self) -> None:
        # Csak a fájlokat takarítjuk; a mappa megmarad a CI-debughoz
        pass

    def test_hypnagogic_disabled_engine_runs_normally(self) -> None:
        """Ha hypnagogic.enabled=False, a Modul A komponensek None maradnak."""
        policy = _strict_immune_with_hypnagogic(self.tmpdir, hypnagogic_enabled=False)
        try:
            registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
            eng = AxiomaticInferenceEngine(
                policy_enabled=True,
                policy_path=str(policy),
                registry_path=str(registry),
            )
            self.assertIsNone(eng._emission_logger)
            self.assertIsNone(eng._fisher_realtime)
            self.assertIsNone(eng._hypnagogic_state)
            # Néhány lépés futtatása nem dob hibát
            for _ in range(50):
                eng.think_step()
            # AWAKE-stílus relaxáció (még akkor is, ha nincs állapotgép)
            relax = eng.get_current_relaxation()
            self.assertEqual(relax["forbidden_weight"], 1.0)
        finally:
            policy.unlink(missing_ok=True)

    def test_hypnagogic_enabled_creates_components(self) -> None:
        """hypnagogic.enabled=True → emission_logger, fisher_realtime, state mind aktív."""
        policy = _strict_immune_with_hypnagogic(self.tmpdir, hypnagogic_enabled=True)
        try:
            registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
            eng = AxiomaticInferenceEngine(
                policy_enabled=True,
                policy_path=str(policy),
                registry_path=str(registry),
            )
            self.assertIsNotNone(eng._emission_logger)
            self.assertIsNotNone(eng._fisher_realtime)
            self.assertIsNotNone(eng._hypnagogic_state)
            # Kezdetben AWAKE-ben
            self.assertEqual(
                eng._hypnagogic_state.current_phase(), HypnagogicPhase.AWAKE
            )
        finally:
            policy.unlink(missing_ok=True)

    def test_emission_records_per_think_step(self) -> None:
        """50 think_step → emission_logger ring buffer növekszik, schema valid."""
        policy = _strict_immune_with_hypnagogic(self.tmpdir, hypnagogic_enabled=True)
        try:
            registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
            eng = AxiomaticInferenceEngine(
                policy_enabled=True,
                policy_path=str(policy),
                registry_path=str(registry),
            )
            for _ in range(50):
                eng.think_step()
            recent = eng._emission_logger.recent(50)
            self.assertEqual(len(recent), 50)
            for r in recent:
                self.assertIn(r["emission"], {
                    "deductive_added", "abductive_added", "rejected", "idle"
                })
                # Schema check
                self.assertIn("step_id", r)
                self.assertIn("tick", r)
                self.assertIn("pair", r)
                self.assertIn("domain_transition", r)
                self.assertIn("reject_reason", r)
        finally:
            policy.unlink(missing_ok=True)

    def test_hypnagogic_episode_writes_log(self) -> None:
        """start_hypnagogic_episode() + 50 think_step → hypnagogic_log.jsonl létrejön."""
        policy = _strict_immune_with_hypnagogic(self.tmpdir, hypnagogic_enabled=True)
        try:
            registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
            eng = AxiomaticInferenceEngine(
                policy_enabled=True,
                policy_path=str(policy),
                registry_path=str(registry),
            )
            # 20 lépés AWAKE-ben (warmup)
            for _ in range(20):
                eng.think_step()
            # Hipnagóg epizód indítás
            self.assertTrue(eng.start_hypnagogic_episode())
            # 30 lépés hipnagóg fázisokon át (entry=5 + deep=15 + exit=5 = 25, +5 buffer)
            for _ in range(30):
                eng.think_step()
            # A log fájl létrejön és nem üres
            log_path = self.tmpdir / "hypnagogic_log.jsonl"
            self.assertTrue(log_path.is_file(), "hypnagogic_log nem keletkezett")
            with log_path.open(encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            self.assertGreater(
                len(lines), 0, "hypnagogic_log üres"
            )
            # Legalább egy bejegyzésnek DEEP fázisban kell lennie
            phases = []
            for ln in lines:
                obj = json.loads(ln)
                phases.append(obj.get("phase"))
                self.assertIn(obj["phase"], {"entry", "deep", "exit"})
            self.assertIn("deep", phases)
        finally:
            policy.unlink(missing_ok=True)

    def test_hypnagogic_relaxation_changes_with_phase(self) -> None:
        """ENTRY → DEEP fázisra a forbidden_weight csökken 1.0-ról 0.3 felé."""
        policy = _strict_immune_with_hypnagogic(self.tmpdir, hypnagogic_enabled=True)
        try:
            registry = ROOT / "experiments" / "registries" / "dense_thesis.json"
            eng = AxiomaticInferenceEngine(
                policy_enabled=True,
                policy_path=str(policy),
                registry_path=str(registry),
            )
            # AWAKE-ben strict
            self.assertEqual(eng.get_current_relaxation()["forbidden_weight"], 1.0)
            # Indítsunk epizódot
            eng.start_hypnagogic_episode()
            # 5 lépés ENTRY → eljutunk DEEP-be
            for _ in range(8):
                eng.think_step()
            self.assertEqual(
                eng._hypnagogic_state.current_phase(), HypnagogicPhase.DEEP
            )
            # DEEP-ben forbidden_weight = 0.3
            self.assertAlmostEqual(
                eng.get_current_relaxation()["forbidden_weight"], 0.3, places=2
            )
        finally:
            policy.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
