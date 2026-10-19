"""Coach evaluation: cost, grounding, guardrail counts and the evaluate_coach command.
The AI model is replaced by a fake LLM, so no API key or network is needed."""
import csv
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings

from ai.crews.diagnosis_crew.evidence import KnownMoves
from apps.coaching.services import diagnosis_service
from evaluation.measure_coaching import cost_usd, evaluate_run, format_summary, grounding, summarize
from tests.fake_llm import FakeLLM, final_answer, weakness
from tests.test_coaching import CoachingTestBase
from tests.test_coaching_crew import RECORDS


def fake_llm(*replies) -> FakeLLM:
    return FakeLLM(model="fake/coach", replies=list(replies))


class CostTests(unittest.TestCase):
    def test_known_models_are_priced_per_million_tokens(self):
        self.assertEqual(cost_usd("anthropic/claude-sonnet-5-5", 12_000, 3_000), 0.054)
        self.assertEqual(cost_usd("claude-haiku-5-5", 1_000_000, 0), 0.1)

    def test_unknown_model_has_no_price(self):
        self.assertIsNone(cost_usd("fake/coach", 100, 20))


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.known = KnownMoves.from_records(RECORDS)

    def test_cited_moves_are_marked_known_or_not(self):
        self.assertEqual(
            self.known.cited_moves("2. Qg4 lost the queen (best was exd5), not Bxf7+."),
            [("2. Qg4", True), ("exd5", True), ("Bxf7+", False)],
        )

    def test_share_of_cited_moves_in_the_data(self):
        weaknesses = [
            weakness(7, evidence="2. Qg4 lost the queen; 5. Qg4 never happened."),
            weakness(7, evidence="41 hanging pieces in 10 games."),
        ]
        self.assertEqual(
            grounding(weaknesses, self.known),
            {"weaknesses_citing_moves": 1, "cited_moves": 2, "grounded_moves": 1, "grounding_pct": 50.0},
        )


class EvaluateRunTests(unittest.TestCase):
    def test_successful_run_counts_the_rejection_and_the_grounding(self):
        row, rubric = evaluate_run(1, RECORDS, fake_llm(final_answer(weakness(99)), final_answer(weakness(7))))
        self.assertTrue(row["success"])
        self.assertEqual((row["rejections"], row["unknown_games_rejections"], row["invented_moves_rejections"]), (1, 1, 0))
        self.assertEqual((row["input_tokens"], row["output_tokens"], row["turns"]), (200, 40, 2))
        self.assertIsNone(row["cost_usd"])
        self.assertEqual((row["weaknesses"], row["cited_moves"], row["grounding_pct"]), (1, 1, 100.0))
        self.assertEqual(rubric[0]["title"], "Hanging pieces")
        self.assertEqual(rubric[0]["run"], 1)

    def test_failed_run_keeps_its_rejections(self):
        invented = final_answer(weakness(7, evidence="12. Nxf7 lost a knight."))
        with self.assertLogs("ai.flows.coaching_flow", level="ERROR"):
            row, rubric = evaluate_run(2, RECORDS, fake_llm(invented, invented, invented))
        self.assertFalse(row["success"])
        self.assertIn("did not pass the checks", row["error"])
        self.assertEqual((row["rejections"], row["invented_moves_rejections"]), (3, 3))
        self.assertEqual(rubric, [])

    def test_summary_over_runs(self):
        ok, _ = evaluate_run(1, RECORDS, fake_llm(final_answer(weakness(7))))
        with self.assertLogs("ai.flows.coaching_flow", level="ERROR"):
            failed, _ = evaluate_run(2, RECORDS, fake_llm(*[final_answer(weakness(99))] * 3))
        summary = summarize([ok, failed])
        self.assertEqual((summary["runs"], summary["successes"]), (2, 1))
        self.assertEqual((summary["rejections"], summary["runs_with_rejections"]), (3, 1))
        self.assertEqual((summary["mean_input_tokens"], summary["grounding_pct"]), (100, 100.0))
        text = format_summary(summary, "fake/coach", games=1, moves=2)
        self.assertIn("1/2 runs ended with an accepted report", text)
        self.assertIn("Failed run: The AI coach's answer did not pass the checks", text)


@override_settings(AI_API_KEY="test-key")
class EvaluateCoachCommandTests(CoachingTestBase):
    def run_command(self, reply, runs=1):
        out_dir = Path(tempfile.mkdtemp())
        with mock.patch.object(diagnosis_service, "_make_llm", side_effect=lambda: fake_llm(reply)):
            call_command(
                "evaluate_coach", "tester", "--runs", str(runs), "--out", str(out_dir / "coach.csv"), stdout=StringIO()
            )
        return out_dir

    def test_results_and_rubric_are_saved(self):
        out_dir = self.run_command(final_answer(weakness(self.game.pk)), runs=2)
        with open(out_dir / "coach.csv", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["success"] for row in rows], ["True", "True"])
        self.assertEqual([row["input_tokens"] for row in rows], ["100", "100"])
        with open(out_dir / "coach_rubric.csv", encoding="utf-8") as handle:
            rubric = list(csv.DictReader(handle))
        self.assertEqual(len(rubric), 2)
        self.assertEqual(rubric[0]["relevant"], "")
        self.assertIn("2/2 runs ended", (out_dir / "coach.txt").read_text(encoding="utf-8"))

    def test_unknown_user_is_refused(self):
        with mock.patch.object(diagnosis_service, "_make_llm", return_value=fake_llm()):
            with self.assertRaisesRegex(CommandError, "No user called 'nobody'"):
                call_command("evaluate_coach", "nobody", stdout=StringIO())

    @override_settings(AI_API_KEY="")
    def test_missing_api_key_is_refused(self):
        with self.assertRaisesRegex(CommandError, "No AI_API_KEY"):
            call_command("evaluate_coach", "tester", stdout=StringIO())