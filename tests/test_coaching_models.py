from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.coaching.models import TrainingPlan, WeaknessReport

WEAKNESS = {
    "title": "Leaving pieces undefended",
    "category": "tactics",
    "explanation": "Pieces are left where they can be taken for free.",
    "evidence": "2 blunders with hanging_piece.",
    "example_game_ids": [1, 2],
    "priority": 1,
}


TASKS = [
    {"theme": "fork", "name": "Forks", "url": "https://lichess.org/training/fork", "puzzles": 6, "done": True},
    {"theme": "endgame", "name": "Endgame", "url": "https://lichess.org/training/endgame", "puzzles": 3, "done": False},
]


class WeaknessReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_new_report_is_queued_and_empty(self):
        report = WeaknessReport.objects.create(user=self.user)
        self.assertEqual(report.status, WeaknessReport.Status.QUEUED)
        self.assertEqual(report.weaknesses, [])
        self.assertEqual(report.tool_calls, [])

    def test_weaknesses_round_trip_as_json(self):
        report = WeaknessReport.objects.create(
            user=self.user, status=WeaknessReport.Status.DONE, summary="Drops pieces.",
            weaknesses=[WEAKNESS], tool_calls=[{"name": "get_mistake_summary", "seconds": 0.01, "is_error": False}],
        )
        report.refresh_from_db()
        self.assertEqual(report.weaknesses[0]["example_game_ids"], [1, 2])
        self.assertEqual(report.tool_calls[0]["name"], "get_mistake_summary")

    def test_reports_are_listed_newest_first(self):
        first = WeaknessReport.objects.create(user=self.user)
        second = WeaknessReport.objects.create(user=self.user)
        self.assertEqual(list(self.user.weakness_reports.all()), [second, first])


class TrainingPlanTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")
        self.report = WeaknessReport.objects.create(user=self.user)

    def test_plan_belongs_to_one_report(self):
        plan = TrainingPlan.objects.create(report=self.report, tasks=TASKS)
        self.assertEqual(self.report.training_plan, plan)
        self.assertEqual(str(plan), "Practice plan for tester")
        with self.assertRaises(IntegrityError):
            TrainingPlan.objects.create(report=self.report)

    def test_progress_counts(self):
        plan = TrainingPlan.objects.create(report=self.report, tasks=TASKS)
        self.assertEqual((plan.done_count, plan.total_puzzles), (1, 9))

    def test_deleting_user_deletes_reports_and_plans(self):
        TrainingPlan.objects.create(report=self.report, tasks=TASKS)
        self.user.delete()
        self.assertEqual(WeaknessReport.objects.count(), 0)
        self.assertEqual(TrainingPlan.objects.count(), 0)