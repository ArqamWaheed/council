"""Tests for the deterministic judge — especially stance clustering.

Run: python -m unittest discover -s tests   (or: python tests/test_judge.py)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jurors import Opinion  # noqa: E402
from run_council import judge  # noqa: E402


def op(name, position, *reasons):
    return Opinion(name, "test-model", position, list(reasons))


class TestStanceClustering(unittest.TestCase):
    def test_same_stance_different_phrasing_is_unanimous(self):
        """Regression: 'No' and 'No, you should not X' must NOT count as a split."""
        d = judge("Should you bonesmash to ascend facially?", [
            op("Juror 1", "No, you should not bonesmash to ascend facially", "self-harm"),
            op("Juror 2", "No", "medical risks"),
        ])
        self.assertTrue(d["unanimous"])
        self.assertEqual(d["split"], "2")
        self.assertEqual(d["confidence"], 1.0)
        self.assertEqual(d["dissents"], [])

    def test_genuine_disagreement_is_contested(self):
        d = judge("Postgres or Mongo?", [
            op("Juror 1", "Use PostgreSQL for the new SaaS", "acid"),
            op("Juror 2", "MongoDB", "flexible schema"),
        ])
        self.assertFalse(d["unanimous"])
        self.assertEqual(d["split"], "1-1")
        self.assertEqual(d["confidence"], 0.5)
        self.assertEqual(len(d["dissents"]), 1)

    def test_equivalent_options_merge(self):
        d = judge("Postgres or Mongo?", [
            op("Juror 1", "Use PostgreSQL for the new SaaS", "acid"),
            op("Juror 2", "PostgreSQL", "mature"),
        ])
        self.assertTrue(d["unanimous"])

    def test_no_code_not_misread_as_negative(self):
        """'no-code' contains 'no' but the stance is not negative."""
        d = judge("No-code tool or write real code?", [
            op("Juror 1", "Build the MVP with a no-code tool", "speed"),
            op("Juror 2", "Write real code for the MVP", "control"),
        ])
        self.assertFalse(d["unanimous"])
        self.assertEqual(d["split"], "1-1")

    def test_yes_vs_no_is_contested(self):
        d = judge("Should we ship Friday?", [
            op("Juror 1", "Yes, ship it", "ready"),
            op("Juror 2", "No, wait", "risky"),
        ])
        self.assertFalse(d["unanimous"])

    def test_three_way_majority(self):
        d = judge("Postgres, Mongo or SQLite?", [
            op("Juror 1", "Postgres", "acid"),
            op("Juror 2", "Postgres for reliability", "mature"),
            op("Juror 3", "SQLite", "simple"),
        ])
        self.assertFalse(d["unanimous"])
        self.assertEqual(d["split"], "2-1")
        self.assertEqual(d["confidence"], round(2 / 3, 2))


if __name__ == "__main__":
    unittest.main()
