"""
Kísérleti infra tesztek:
- random_registry determinisztikus seed mellett.
- symmetric_immunity_registry: minden tilalom szimmetrikus.
- random_seed a policy-ben → engine think_step szekvencia reprodukálható.
- aggregate.py log-parser felismeri az eredeti telemetria-formátumot.
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
from experiments.aggregate import _parse_log
from experiments.registry_generators import (
    random_registry,
    symmetric_immunity_registry,
)


class RegistryGeneratorTests(unittest.TestCase):
    def test_random_registry_deterministic(self) -> None:
        a = random_registry(20, 0.05, seed=123)
        b = random_registry(20, 0.05, seed=123)
        self.assertEqual(a["causal_edges"], b["causal_edges"])

    def test_random_registry_changes_with_seed(self) -> None:
        a = random_registry(20, 0.05, seed=1)
        b = random_registry(20, 0.05, seed=2)
        self.assertNotEqual(a["causal_edges"], b["causal_edges"])

    def test_random_registry_no_self_loops(self) -> None:
        d = random_registry(20, 0.5, seed=1)
        for src, dst in d["causal_edges"]:
            self.assertNotEqual(src, dst)

    def test_random_registry_no_forbidden_or_negation(self) -> None:
        d = random_registry(15, 0.1, seed=1)
        self.assertEqual(d["forbidden_edges"], [])
        self.assertEqual(d["logical_negation_pairs"], [])

    def test_symmetric_immunity_makes_forbidden_symmetric(self) -> None:
        # Minimal source: 3 csúcs, 1 forbidden él
        src = {
            "version": "t",
            "nodes": [
                {"id": "X", "domain": "L", "formula": "", "variables": [], "keywords": ["x"]},
                {"id": "Y", "domain": "L", "formula": "", "variables": [], "keywords": ["y"]},
                {"id": "Z", "domain": "L", "formula": "", "variables": [], "keywords": ["z"]},
            ],
            "logical_negation_pairs": [],
            "causal_edges": [["X", "Y"]],
            "forbidden_edges": [["Y", "X"]],
        }
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as tf:
            json.dump(src, tf, ensure_ascii=False)
            tmp_path = Path(tf.name)
        try:
            sym = symmetric_immunity_registry(tmp_path)
            forbidden = {tuple(p) for p in sym["forbidden_edges"]}
            self.assertIn(("Y", "X"), forbidden)
            self.assertIn(("X", "Y"), forbidden)
        finally:
            tmp_path.unlink(missing_ok=True)


class SeedReproducibilityTests(unittest.TestCase):
    """A random_seed policy-mező determinisztikussá teszi a think_step-et."""

    def _make_policy(self, telemetry_path: Path, seed: int) -> Path:
        data = {
            "discovery": {
                "enabled": True,
                "telemetry_enabled": False,
                "log_path": str(telemetry_path) + ".disc",
                "telemetry_log_path": str(telemetry_path),
                "random_seed": seed,
                "seed_hamilton_ring": True,
            }
        }
        tf = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        yaml.safe_dump(data, tf, allow_unicode=True)
        tf.close()
        return Path(tf.name)

    def _run(self, seed: int, n_steps: int) -> list:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".log", delete=False
        ) as tf:
            tel = Path(tf.name)
        policy_path = self._make_policy(tel, seed)
        try:
            eng = AxiomaticInferenceEngine(
                policy_enabled=True, policy_path=str(policy_path)
            )
            qs = []
            for _ in range(n_steps):
                _, q = eng.think_step()
                qs.append(round(q, 8))
            return qs
        finally:
            policy_path.unlink(missing_ok=True)
            tel.unlink(missing_ok=True)

    def test_same_seed_produces_same_q_sequence(self) -> None:
        a = self._run(seed=7, n_steps=50)
        b = self._run(seed=7, n_steps=50)
        self.assertEqual(a, b)

    def test_different_seeds_diverge(self) -> None:
        a = self._run(seed=1, n_steps=200)
        b = self._run(seed=2, n_steps=200)
        # Legalább egy ponton eltér (különben nincs reális randomizáció).
        self.assertNotEqual(a, b)


class TelemetryParserTests(unittest.TestCase):
    def test_parse_real_telemetry_format(self) -> None:
        sample = (
            "PID=16196 [TICK: 50] Q=0.0198 | DIST(MACRO->MICRO)=2 | "
            "B_EFFICIENCY=0.85 | TOPO=9 | RRR=0.0000 | ASYM=1.0000\n"
            "PID=16196 [TICK: 100] Q=0.0312 | DIST(MACRO->MICRO)=inf | "
            "B_EFFICIENCY=0.85 | TOPO=14 | RRR=0.0000 | ASYM=0.9876\n"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".log", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(sample)
            log_path = Path(tf.name)
        try:
            parsed = _parse_log(log_path)
            self.assertIn(50, parsed)
            self.assertIn(100, parsed)
            self.assertAlmostEqual(parsed[50]["q"], 0.0198)
            self.assertEqual(parsed[50]["topo"], 9.0)
            self.assertAlmostEqual(parsed[100]["asym"], 0.9876)
            # inf dist -> NaN
            import math
            self.assertTrue(math.isnan(parsed[100]["dist"]))
        finally:
            log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
