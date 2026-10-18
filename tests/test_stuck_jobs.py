"""Analyses and reports left 'in progress' when the worker stops must not block the user forever."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.coaching.models import WeaknessReport
from apps.coaching.services import coaching_service
from apps.games.models import Game
from apps.games.repositories import game_repository
from apps.games.services import game_service
from tests.test_game_pages import DUMMY_TASKS

User = get_user_model()
PGN = "1. e4 e5 *"


def make_old(obj, minutes=31):
    type(obj).objects.filter(pk=obj.pk).update(status_changed_at=timezone.now() - timedelta(minutes=minutes))


@override_settings(TASKS=DUMMY_TASKS, STUCK_JOB_MINUTES=30, AI_API_KEY="test-key")
class StuckJobTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.client.login(username="tester", password="pass12345")

    def game(self, **fields):
        return Game.objects.create(user=self.user, pgn=PGN, **fields)

    @override_settings(MAX_ANALYSIS_QUEUE=2)
    def test_stuck_games_free_the_analysis_queue(self):
        stuck = [self.game(status=Game.Status.RUNNING), self.game(status=Game.Status.QUEUED)]
        for game in stuck:
            make_old(game)
        waiting = self.game()
        self.assertEqual(game_service.request_analysis(waiting), game_service.QUEUED)
        for game in stuck:
            game.refresh_from_db()
            self.assertEqual(game.status, Game.Status.FAILED)
            self.assertIn("stopped before it finished", game.analysis_error)

    @override_settings(MAX_ANALYSIS_QUEUE=2)
    def test_recent_games_still_fill_the_queue(self):
        self.game(status=Game.Status.RUNNING)
        self.game(status=Game.Status.QUEUED)
        self.assertEqual(game_service.request_analysis(self.game()), game_service.QUEUE_FULL)

    def test_stuck_game_shows_as_failed_on_its_page_and_status_check(self):
        game = self.game(status=Game.Status.RUNNING)
        make_old(game)
        status = self.client.get(reverse("game_status", args=[game.pk])).json()
        self.assertEqual(status["status"], "failed")
        self.assertContains(self.client.get(reverse("game_detail", args=[game.pk])), "stopped before it finished")

    def test_stuck_report_no_longer_blocks_a_new_one(self):
        ready = self.game(status=Game.Status.DONE, user_color="white")
        stuck = WeaknessReport.objects.create(user=self.user, status=WeaknessReport.Status.RUNNING)
        make_old(stuck)
        response = self.client.post(reverse("create_report"), {"games": [ready.pk]}, follow=True)
        self.assertNotContains(response, "already being prepared")
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, WeaknessReport.Status.FAILED)
        self.assertEqual(WeaknessReport.objects.filter(status=WeaknessReport.Status.QUEUED).count(), 1)

    def test_recent_report_still_blocks(self):
        ready = self.game(status=Game.Status.DONE, user_color="white")
        WeaknessReport.objects.create(user=self.user, status=WeaknessReport.Status.RUNNING)
        response = self.client.post(reverse("create_report"), {"games": [ready.pk]}, follow=True)
        self.assertContains(response, "already being prepared")

    def test_stuck_report_shows_as_failed_on_the_status_check(self):
        report = WeaknessReport.objects.create(user=self.user, status=WeaknessReport.Status.QUEUED)
        make_old(report)
        self.assertEqual(self.client.get(reverse("report_status", args=[report.pk])).json()["status"], "failed")

    def test_other_users_jobs_are_left_alone(self):
        other = User.objects.create_user("other", password="pass12345")
        theirs = Game.objects.create(user=other, pgn=PGN, status=Game.Status.RUNNING)
        make_old(theirs)
        game_service.recover_stuck_games(self.user)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, Game.Status.RUNNING)

    def test_status_change_updates_the_time(self):
        game = self.game()
        make_old(game, minutes=60)
        game_repository.set_status(game, Game.Status.QUEUED)
        game.refresh_from_db()
        self.assertGreater(game.status_changed_at, timezone.now() - timedelta(minutes=1))

    def test_requests_lock_the_user_so_checks_cannot_run_twice_at_once(self):
        ready = self.game(status=Game.Status.DONE, user_color="white")
        with mock.patch("apps.accounts.repositories.account_repository.lock_user") as lock:
            coaching_service.request_report(self.user, [ready.pk])
            game_service.request_analysis(self.game())
        self.assertEqual(lock.call_count, 2)
        lock.assert_called_with(self.user)


class RecoverStuckJobsCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")

    def test_command_fails_only_old_jobs(self):
        old_game = Game.objects.create(user=self.user, pgn=PGN, status=Game.Status.RUNNING)
        new_game = Game.objects.create(user=self.user, pgn=PGN, status=Game.Status.QUEUED)
        old_report = WeaknessReport.objects.create(user=self.user, status=WeaknessReport.Status.RUNNING)
        make_old(old_game)
        make_old(old_report)
        out = StringIO()
        call_command("recover_stuck_jobs", stdout=out)
        self.assertIn("Marked 1 stuck game analyses and 1 stuck reports as failed.", out.getvalue())
        for obj, status in ((old_game, "failed"), (new_game, "queued"), (old_report, "failed")):
            obj.refresh_from_db()
            self.assertEqual(obj.status, status)

    def test_minutes_zero_fails_everything_in_progress(self):
        Game.objects.create(user=self.user, pgn=PGN, status=Game.Status.QUEUED)
        out = StringIO()
        call_command("recover_stuck_jobs", "--minutes", "0", stdout=out)
        self.assertIn("Marked 1 stuck game analyses", out.getvalue())