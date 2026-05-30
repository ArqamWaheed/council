"""Tests for the deterministic judge — especially stance clustering.

Run: python -m unittest discover -s tests   (or: python tests/test_judge.py)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jurors import Opinion, _parse  # noqa: E402
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


class TestParsing(unittest.TestCase):
    def test_markdown_position_label_is_stripped(self):
        """Regression: '**POSITION:** Postgres...' must parse to the stance, not 'POSITION'."""
        pos, _ = _parse("**POSITION:** Postgres is the best choice\n1. acid\n2. mature")
        self.assertNotEqual(pos.lower(), "position")
        self.assertTrue(pos.lower().startswith("postgres"))

    def test_markdown_emphasis_stripped_from_reasons(self):
        _, reasons = _parse("POSITION: PostgreSQL\n1. **Data Integrity**: ACID compliance\n2. `Maturity`: ecosystem")
        self.assertEqual(reasons[0], "Data Integrity: ACID compliance")
        self.assertEqual(reasons[1], "Maturity: ecosystem")

    def test_three_postgres_phrasings_are_unanimous(self):
        """The exact reported bug: 3 jurors all favoring Postgres, varied phrasing -> unanimous."""
        d = judge("Postgres or Mongo for a new SaaS?", [
            op("Juror 1", *["Postgres is the better choice for a new SaaS"]),
            op("Juror 2", *["PostgreSQL"]),
            op("Local Juror", *["Postgres"]),
        ])
        self.assertTrue(d["unanimous"])
        self.assertEqual(d["dissents"], [])

    def test_option_question_real_split(self):
        d = judge("Postgres or Mongo for a new SaaS?", [
            op("Juror 1", *["Postgres is the better choice"]),
            op("Juror 2", *["Mongo, for flexible documents"]),
            op("Local Juror", *["Postgres for ACID"]),
        ])
        self.assertFalse(d["unanimous"])
        self.assertEqual(d["split"], "2-1")

    def test_vague_position_uses_reasons_to_pick_option(self):
        """Regression: a small model's vague position must cluster by its reasons, not split.

        Real case: Local Juror's position had no option keyword but its reason clearly
        endorsed PostgreSQL ('...compared to ... like MongoDB') — it must NOT count as dissent."""
        d = judge("Postgres or Mongo for a new SaaS?", [
            op("Juror 1", "PostgreSQL", "ACID guarantees"),
            op("Juror 2", "Postgres is the better choice", "mature ecosystem"),
            op("Local Juror", "To facilitate efficient integration and scalability",
               "PostgreSQL has proven reliability and security compared to other RDBMSs like MongoDB"),
        ])
        self.assertTrue(d["unanimous"])
        self.assertEqual(d["dissents"], [])

    def test_comparison_mention_not_counted_as_endorsement(self):
        from run_council import _option_of
        # Mentions Mongo only as the thing it's better THAN -> endorses Postgres.
        self.assertEqual(
            _option_of("", ["postgres", "mongo"],
                       ["postgres scales better than mongo for relational data"]),
            "postgres")


class TestReflect(unittest.TestCase):
    """The --reflect learning loop: evidence, rule validation, offline suggestion."""

    def _records(self):
        return [
            {"topic": "database", "split": "2-1", "verdict": "favors Postgres",
             "dissents": ["Local Juror argued 'Mongo': flexible", "x"],
             "jurors": [{"name": "Juror 1"}, {"name": "Juror 2"}, {"name": "Local Juror"}]},
            {"topic": "database", "split": "2-1", "verdict": "favors Postgres",
             "dissents": ["Local Juror argued 'Mongo': scale"],
             "jurors": [{"name": "Juror 1"}, {"name": "Juror 2"}, {"name": "Local Juror"}]},
        ]

    def test_evidence_tally_counts_dissents(self):
        from run_council import reflection_evidence
        lines, tally = reflection_evidence(self._records())
        self.assertEqual(len(lines), 2)
        self.assertEqual(tally[("local juror", "database")], [2, 2])
        self.assertEqual(tally[("juror 1", "database")], [0, 2])

    def test_valid_rule_accepts_and_rejects(self):
        from run_council import _valid_rule
        self.assertEqual(_valid_rule("Local Juror | security | 1.5"),
                         "Local Juror | security | 1.5")
        self.assertEqual(_valid_rule("Nobody | security | 1.5"), "")   # unknown juror
        self.assertEqual(_valid_rule("Local Juror | cooking | 1.5"), "")  # unknown topic
        self.assertEqual(_valid_rule("Local Juror | security | 1.0"), "")  # no-op weight
        self.assertEqual(_valid_rule("Local Juror | security | 99"), "")   # out of range

    def test_offline_suggestion_targets_repeat_dissenter(self):
        os.environ["HERMES_ORCHESTRATION"] = "0"   # force the deterministic path
        from run_council import suggest_weight
        s = suggest_weight(self._records())
        self.assertIsNotNone(s)
        self.assertEqual(s["via"], "offline-heuristic")
        self.assertTrue(s["rule"].lower().startswith("local juror | database |"))

    def test_no_suggestion_without_enough_history(self):
        from run_council import suggest_weight
        self.assertIsNone(suggest_weight(self._records()[:1]))

    def test_parse_weights_filters_invalid(self):
        from run_council import parse_weights
        w = parse_weights([
            "Local Juror | database | 1.5",   # valid
            "Ghost | database | 1.5",         # unknown juror -> dropped
            "Local Juror | database | 1.0",   # no-op -> dropped
            "garbage",                        # malformed -> dropped
        ])
        self.assertEqual(w, {("local juror", "database"): 1.5})

    def test_extra_weights_flip_the_verdict(self):
        """Client-supplied weights (e.g. browser localStorage) must sway the judge."""
        jurors = [
            op("Juror 1", "Postgres is better"),
            op("Juror 2", "Postgres for ACID"),
            op("Local Juror", "Mongo for flexibility"),
        ]
        base = judge("Postgres or Mongo for a new SaaS?", jurors)
        self.assertIn("Postgres", base["verdict"])
        # Upweight the lone Mongo dissenter enough to win (1 vs 2 -> 3 vs 2).
        swayed = judge("Postgres or Mongo for a new SaaS?", jurors,
                       {("local juror", "database"): 3.0})
        self.assertIn("Mongo", swayed["verdict"])


class TestDebate(unittest.TestCase):
    """Round 2 deliberation: jurors see each other's positions and may hold or change."""

    def test_disagreement_detection(self):
        from jurors import _has_disagreement
        self.assertFalse(_has_disagreement([op("A", "Postgres"), op("B", "postgres ")]))
        self.assertTrue(_has_disagreement([op("A", "Postgres"), op("B", "Mongo")]))

    def test_leading_position_is_most_held(self):
        from jurors import _leading_position
        self.assertEqual(
            _leading_position([op("A", "Postgres"), op("B", "Postgres"), op("C", "Mongo")]),
            "Postgres")

    def test_mock_rebut_persuaded_changes_to_leading(self):
        from jurors import _mock_rebut
        o = _mock_rebut(op("Local Juror", "Mongo"), "Postgres", persuaded=True)
        self.assertTrue(o.changed_mind)
        self.assertEqual(o.position, "Postgres")
        self.assertEqual(o.original_position, "Mongo")
        self.assertTrue(o.deliberated)
        self.assertTrue(o.rebuttal)

    def test_mock_rebut_unpersuaded_holds(self):
        from jurors import _mock_rebut
        o = _mock_rebut(op("Local Juror", "Mongo"), "Postgres", persuaded=False)
        self.assertFalse(o.changed_mind)
        self.assertEqual(o.position, "Mongo")
        self.assertTrue(o.deliberated)

    def test_persuaded_juror_already_on_leading_holds(self):
        """A juror already on the leading side never 'changes' even if persuaded-bit is set."""
        from jurors import _mock_rebut
        o = _mock_rebut(op("Juror 1", "Postgres"), "Postgres", persuaded=True)
        self.assertFalse(o.changed_mind)

    def test_judge_surfaces_debate_shift(self):
        changed = op("Juror 2", "Postgres", "acid")
        changed.original_position = "Mongo"
        changed.changed_mind = True
        changed.deliberated = True
        changed.rebuttal = "Postgres' ACID guarantees win me over."
        d = judge("Postgres or Mongo for a new SaaS?", [
            op("Juror 1", "Postgres", "mature"), changed,
        ])
        self.assertTrue(d["debated"])
        self.assertEqual(len(d["shifts"]), 1)
        self.assertIn("Juror 2", d["shifts"][0])
        j2 = next(j for j in d["jurors"] if j["name"] == "Juror 2")
        self.assertTrue(j2["changed_mind"])
        self.assertEqual(j2["original_position"], "Mongo")
        self.assertEqual(j2["rebuttal"], "Postgres' ACID guarantees win me over.")

    def test_offline_convene_debate_is_deterministic(self):
        os.environ["OPENROUTER_API_KEY"] = ""
        os.environ["HERMES_ORCHESTRATION"] = "0"
        from jurors import convene
        a = convene("Postgres or Mongo for a new SaaS?")
        b = convene("Postgres or Mongo for a new SaaS?")
        self.assertTrue(all(o.mocked for o in a))
        self.assertTrue(all(o.deliberated for o in a))   # round 2 ran (round 1 disagreed)
        self.assertEqual([(o.position, o.changed_mind) for o in a],
                         [(o.position, o.changed_mind) for o in b])

    def test_debate_skipped_when_disabled(self):
        os.environ["OPENROUTER_API_KEY"] = ""
        os.environ["HERMES_ORCHESTRATION"] = "0"
        os.environ["COUNCIL_DEBATE"] = "0"
        try:
            from jurors import convene
            ops = convene("Postgres or Mongo for a new SaaS?")
            self.assertFalse(any(o.deliberated for o in ops))
        finally:
            os.environ.pop("COUNCIL_DEBATE", None)


if __name__ == "__main__":
    unittest.main()