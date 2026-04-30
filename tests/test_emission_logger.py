"""Unit tests for ``emission_logger.EmissionLogger``."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from emission_logger import EmissionLogger  # noqa: E402


def make_snapshot(
    *,
    mode: str = "heuristic",
    i: Optional[int] = 0,
    j: Optional[int] = 1,
    verified: Optional[bool] = True,
    edge_added: bool = True,
    abductive: bool = False,
    edge_reject: Optional[str] = None,
) -> Any:
    """Build a duck-typed snapshot stub."""
    return SimpleNamespace(
        mode=mode,
        i=i,
        j=j,
        verified=verified,
        edge_added=edge_added,
        abductive=abductive,
        edge_reject=edge_reject,
    )


class EmissionClassificationTests(unittest.TestCase):
    """Cover the four emission classes and reject reason mapping."""

    def test_idle_sparse_yields_idle(self) -> None:
        """idle_sparse mode -> emission=='idle' and pair is None."""
        logger = EmissionLogger()
        snap = make_snapshot(mode="idle_sparse", i=None, j=None,
                             verified=None, edge_added=False)
        rec = logger.record(0, 5, snap)
        self.assertEqual(rec["emission"], "idle")
        self.assertIsNone(rec["pair"])
        self.assertIsNone(rec["reject_reason"])
        self.assertFalse(rec["domain_transition"])

    def test_idle_when_indices_missing(self) -> None:
        """Missing i or j (even if mode != idle_sparse) -> idle."""
        logger = EmissionLogger()
        rec = logger.record(1, 6, make_snapshot(i=None, j=2, edge_added=False,
                                                verified=None))
        self.assertEqual(rec["emission"], "idle")
        self.assertIsNone(rec["pair"])

    def test_deductive_added(self) -> None:
        """edge_added & verified & not abductive -> deductive_added with pair."""
        logger = EmissionLogger()
        rec = logger.record(2, 10, make_snapshot(
            i=3, j=7, verified=True, edge_added=True, abductive=False))
        self.assertEqual(rec["emission"], "deductive_added")
        self.assertEqual(rec["pair"], [3, 7])
        self.assertIsInstance(rec["pair"], list)
        self.assertIsNone(rec["reject_reason"])

    def test_abductive_added(self) -> None:
        """edge_added & abductive (verified=False) -> abductive_added."""
        logger = EmissionLogger()
        rec = logger.record(3, 11, make_snapshot(
            i=2, j=4, verified=False, edge_added=True, abductive=True))
        self.assertEqual(rec["emission"], "abductive_added")
        self.assertEqual(rec["pair"], [2, 4])
        self.assertIsNone(rec["reject_reason"])

    def test_rejected_forbidden(self) -> None:
        """edge_reject 'forbidden' -> emission rejected, reason forbidden."""
        logger = EmissionLogger()
        rec = logger.record(4, 12, make_snapshot(
            i=1, j=2, verified=True, edge_added=False, edge_reject="forbidden"))
        self.assertEqual(rec["emission"], "rejected")
        self.assertEqual(rec["reject_reason"], "forbidden")

    def test_rejected_contradiction_maps_to_negation(self) -> None:
        """edge_reject 'contradiction' -> reject_reason renamed to 'negation'."""
        logger = EmissionLogger()
        rec = logger.record(5, 13, make_snapshot(
            i=1, j=2, verified=False, edge_added=False,
            edge_reject="contradiction"))
        self.assertEqual(rec["emission"], "rejected")
        self.assertEqual(rec["reject_reason"], "negation")

    def test_rejected_exists(self) -> None:
        """edge_reject 'exists' -> reject_reason 'exists'."""
        logger = EmissionLogger()
        rec = logger.record(6, 14, make_snapshot(
            i=1, j=2, verified=True, edge_added=False, edge_reject="exists"))
        self.assertEqual(rec["emission"], "rejected")
        self.assertEqual(rec["reject_reason"], "exists")

    def test_rejected_unknown_reason_maps_to_none(self) -> None:
        """Unmapped edge_reject (e.g. 'no_hypothesis') -> reject_reason None."""
        logger = EmissionLogger()
        rec = logger.record(7, 15, make_snapshot(
            i=1, j=2, verified=False, edge_added=False,
            edge_reject="no_hypothesis"))
        self.assertEqual(rec["emission"], "rejected")
        self.assertIsNone(rec["reject_reason"])


class DomainTransitionTests(unittest.TestCase):
    """Verify domain_transition derivation against axiom_labels."""

    def test_domain_transition_true_when_domains_differ(self) -> None:
        """axiom_labels[i] != axiom_labels[j] -> domain_transition True."""
        labels = {0: "LOGIC", 1: "PHYSICS", 2: "LOGIC"}
        logger = EmissionLogger(axiom_labels=labels)
        rec = logger.record(0, 1, make_snapshot(i=0, j=1))
        self.assertTrue(rec["domain_transition"])

    def test_domain_transition_false_when_domains_equal(self) -> None:
        """axiom_labels[i] == axiom_labels[j] -> domain_transition False."""
        labels = {0: "LOGIC", 1: "PHYSICS", 2: "LOGIC"}
        logger = EmissionLogger(axiom_labels=labels)
        rec = logger.record(0, 1, make_snapshot(i=0, j=2))
        self.assertFalse(rec["domain_transition"])

    def test_domain_transition_false_when_labels_none(self) -> None:
        """axiom_labels=None -> domain_transition always False."""
        logger = EmissionLogger(axiom_labels=None)
        rec = logger.record(0, 1, make_snapshot(i=0, j=1))
        self.assertFalse(rec["domain_transition"])

    def test_domain_transition_false_when_label_missing(self) -> None:
        """Missing entry for an index -> domain_transition False."""
        labels = {0: "LOGIC"}  # no entry for 1
        logger = EmissionLogger(axiom_labels=labels)
        rec = logger.record(0, 1, make_snapshot(i=0, j=1))
        self.assertFalse(rec["domain_transition"])


class RingBufferTests(unittest.TestCase):
    """Verify ring buffer FIFO cap and recent()/clear()."""

    def test_ring_buffer_cap_enforced(self) -> None:
        """Adding 2500 records with cap 2000 keeps only the last 2000."""
        logger = EmissionLogger(ring_buffer_size=2000)
        for k in range(2500):
            logger.record(k, k, make_snapshot(i=0, j=1))
        all_recent = logger.recent(2500)
        self.assertEqual(len(all_recent), 2000)
        # FIFO: first kept record should have step_id = 500
        self.assertEqual(all_recent[0]["step_id"], 500)
        self.assertEqual(all_recent[-1]["step_id"], 2499)

    def test_recent_default_returns_all(self) -> None:
        """recent() with no argument returns all buffered records."""
        logger = EmissionLogger(ring_buffer_size=10)
        for k in range(5):
            logger.record(k, k, make_snapshot(i=0, j=1))
        self.assertEqual(len(logger.recent()), 5)

    def test_recent_n_slices(self) -> None:
        """recent(n) returns the last n records in order."""
        logger = EmissionLogger(ring_buffer_size=10)
        for k in range(5):
            logger.record(k, k, make_snapshot(i=0, j=1))
        last2 = logger.recent(2)
        self.assertEqual([r["step_id"] for r in last2], [3, 4])

    def test_clear_empties_buffer(self) -> None:
        """clear() empties the in-memory buffer."""
        logger = EmissionLogger()
        logger.record(0, 0, make_snapshot(i=0, j=1))
        logger.clear()
        self.assertEqual(logger.recent(), [])


class JsonlPersistenceTests(unittest.TestCase):
    """Verify JSONL writes one parseable line per record with schema fields."""

    def test_jsonl_one_line_per_record_and_schema(self) -> None:
        """JSONL file gets one line per record; lines parse to schema dicts."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "subdir" / "emissions.jsonl"
            logger = EmissionLogger(log_path=path)

            logger.record(0, 1, make_snapshot(
                i=2, j=3, verified=True, edge_added=True))
            logger.record(1, 2, make_snapshot(
                mode="idle_sparse", i=None, j=None,
                verified=None, edge_added=False))
            logger.record(2, 3, make_snapshot(
                i=4, j=5, verified=False, edge_added=False,
                edge_reject="contradiction"))

            self.assertTrue(path.exists())
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)

            expected_keys = {
                "step_id", "tick", "emission", "pair",
                "domain_transition", "reject_reason",
            }
            parsed = [json.loads(line) for line in lines]
            for rec in parsed:
                self.assertEqual(set(rec.keys()), expected_keys)
                self.assertIsInstance(rec["step_id"], int)
                self.assertIsInstance(rec["tick"], int)
                self.assertIsInstance(rec["emission"], str)
                self.assertIsInstance(rec["domain_transition"], bool)

            # specific field checks
            self.assertEqual(parsed[0]["emission"], "deductive_added")
            self.assertEqual(parsed[0]["pair"], [2, 3])
            self.assertEqual(parsed[1]["emission"], "idle")
            self.assertIsNone(parsed[1]["pair"])
            self.assertEqual(parsed[2]["emission"], "rejected")
            self.assertEqual(parsed[2]["reject_reason"], "negation")


if __name__ == "__main__":
    unittest.main()
