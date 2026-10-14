"""Coaching: building the agent's input, running a report, and the pages.
The AI model is replaced by a fake LLM, so no API key or network is needed."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.coaching.models import TrainingPlan, WeaknessReport
from apps.coaching.services import diagnosis_service
from apps.games.models import Game, Mistake, Move
from tests.fake_llm import FakeLLM, final_answer, use_tool, weakness

User = get_user_model()
IMMEDIATE_TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
DUMMY_TASKS = {"default": {"BACKEND": "django.tasks.backends.dummy.DummyBackend"}}

PGN = '[White "tester"]\n[Black "rival"]\n[Opening "Scandinavian Defense"]\n\n1. e4 d5 2. Qg4 Bxg4 0-1'
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
AFTER_D5 = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def fake_llm(*replies) -> FakeLLM:
    return FakeLLM(model="fake/coach", replies=list(replies))


class CoachingTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.client.login(username="tester", password="pass12345")
        self.game = Game.objects.create(
            user=self.user, pgn=PGN, white="tester", black="rival", result="0-1",
            status=Game.Status.DONE, user_color="white",
        )
        Move.objects.create(game=self.game, ply=1, color="white", san="e4", uci="e2e4",
                            fen_before=START, eval_before=30, eval_after=30, best_move_uci="e2e4", cp_loss=0)
        Move.objects.create(game=self.game, ply=2, color="black", san="d5", uci="d7d5",
                            fen_before=AFTER_E4, eval_before=30, eval_after=40, best_move_uci="e7e5", cp_loss=10)
        qg4 = Move.objects.create(game=self.game, ply=3, color="white", san="Qg4", uci="d1g4",
                                  fen_before=AFTER_D5, eval_before=40, eval_after=-900,
                                  best_move_uci="e4d5", cp_loss=940)
        Mistake.objects.create(move=qg4, severity="blunder", phase="opening", motif="hanging_piece")

    def choose(self, *games):
        """POST data that ticks the given games (default: the test game)."""
        return {"games": [g.pk for g in (games or [self.game])]}


class BuildMoveRecordsTests(CoachingTestBase):
    def test_only_the_users_own_moves_are_used(self):
        records = diagnosis_service.build_move_records(self.user)
        self.assertEqual([r.san for r in records], ["e4", "Qg4"])

    def test_mistakes_and_opening_are_included(self):
        qg4 = diagnosis_service.build_move_records(self.user)[1]
        self.assertEqual((qg4.severity, qg4.motif, qg4.phase), ("blunder", "hanging_piece", "opening"))
        self.assertEqual(qg4.opening, "Scandinavian Defense")

    def test_games_with_unknown_side_are_skipped(self):
        self.game.user_color = ""
        self.game.save()
        self.assertEqual(diagnosis_service.build_move_records(self.user), [])


@override_settings(TASKS=IMMEDIATE_TASKS, AI_API_KEY="test-key")
class ReportFlowTests(CoachingTestBase):
    def test_new_report_runs_the_agent_and_shows_the_result(self):
        llm = fake_llm(use_tool("get_mistake_summary"), final_answer(weakness(self.game.pk)))
        with mock.patch.object(diagnosis_service, "_make_llm", return_value=llm):
            response = self.client.post(reverse("create_report"), self.choose(), follow=True)

        report = WeaknessReport.objects.get()
        self.assertEqual(report.status, WeaknessReport.Status.DONE)
        self.assertEqual((report.games_count, report.moves_count, report.turns), (1, 2, 2))
        self.assertEqual((report.ai_model, report.input_tokens, report.output_tokens), ("fake/coach", 200, 40))
        self.assertIn("Player: tester", str(llm.prompts[0]))
        self.assertRedirects(response, reverse("report_detail", args=[report.pk]))
        self.assertContains(response, "Hanging pieces")
        self.assertContains(response, reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, "get_mistake_summary")
        # Weakness and cure are shown together, followed by the practice list.
        self.assertContains(response, "How to improve")
        self.assertContains(response, "10 hanging-piece puzzles a day")
        self.assertEqual(list(report.games.all()), [self.game])
        # 2. Qg4 was a hanging-piece blunder -> 3 hanging-piece puzzles, built by code.
        task = report.training_plan.tasks[0]
        self.assertEqual((task["theme"], task["puzzles"]), ("hangingPiece", 3))
        self.assertContains(response, "https://lichess.org/training/hangingPiece")
        self.assertContains(response, "3 × Hanging pieces puzzles")

    def test_agent_error_is_shown_on_the_report(self):
        llm = fake_llm(RuntimeError("The AI service is overloaded."))
        with mock.patch.object(diagnosis_service, "_make_llm", return_value=llm):
            response = self.client.post(reverse("create_report"), self.choose(), follow=True)
        self.assertEqual(WeaknessReport.objects.get().status, WeaknessReport.Status.FAILED)
        self.assertEqual(TrainingPlan.objects.count(), 0)
        self.assertContains(response, "could not finish the report")

    @override_settings(AI_API_KEY="")
    def test_missing_api_key_fails_with_a_clear_message(self):
        response = self.client.post(reverse("create_report"), self.choose(), follow=True)
        self.assertContains(response, "No AI_API_KEY")

    def test_only_the_chosen_games_are_studied(self):
        other = Game.objects.create(user=self.user, pgn=PGN, status=Game.Status.DONE, user_color="black")
        llm = fake_llm(final_answer(weakness(self.game.pk)))
        with mock.patch.object(diagnosis_service, "_make_llm", return_value=llm):
            self.client.post(reverse("create_report"), self.choose(self.game))
        self.assertIn("Analysed: 1 games, 2 of their moves.", str(llm.prompts[0]))
        self.assertNotIn(other, WeaknessReport.objects.get().games.all())

    def test_choosing_no_games_gives_a_message_and_no_report(self):
        response = self.client.post(reverse("create_report"), {}, follow=True)
        self.assertEqual(WeaknessReport.objects.count(), 0)
        self.assertContains(response, "Choose at least one game")

    def test_games_that_are_not_ready_are_rejected(self):
        self.game.user_color = ""
        self.game.save()
        response = self.client.post(reverse("create_report"), self.choose(), follow=True)
        self.assertEqual(WeaknessReport.objects.count(), 0)
        self.assertContains(response, "not ready")

    def test_someone_elses_game_cannot_be_chosen(self):
        intruder = User.objects.create_user("intruder", password="pass12345")
        foreign = Game.objects.create(user=intruder, pgn=PGN, status=Game.Status.DONE, user_color="white")
        response = self.client.post(reverse("create_report"), self.choose(foreign), follow=True)
        self.assertEqual(WeaknessReport.objects.count(), 0)
        self.assertContains(response, "not ready")


@override_settings(TASKS=DUMMY_TASKS)
class ReportPageTests(CoachingTestBase):
    def test_queued_report_shows_progress_and_blocks_a_second_one(self):
        self.client.post(reverse("create_report"), self.choose())
        report = WeaknessReport.objects.get()
        page = self.client.get(reverse("report_detail", args=[report.pk]))
        self.assertContains(page, 'id="report-progress"')
        again = self.client.post(reverse("create_report"), self.choose(), follow=True)
        self.assertContains(again, "already being prepared")
        self.assertEqual(WeaknessReport.objects.count(), 1)

    def test_status_endpoint(self):
        report = WeaknessReport.objects.create(user=self.user)
        response = self.client.get(reverse("report_status", args=[report.pk]))
        self.assertEqual(response.json(), {"status": "queued", "label": "Waiting"})

    def test_other_users_cannot_see_a_report(self):
        report = WeaknessReport.objects.create(user=self.user)
        User.objects.create_user("intruder", password="pass12345")
        self.client.login(username="intruder", password="pass12345")
        self.assertEqual(self.client.get(reverse("report_detail", args=[report.pk])).status_code, 404)

    def test_coaching_home_counts_games(self):
        Game.objects.create(user=self.user, pgn=PGN, status=Game.Status.DONE)  # side unknown
        Game.objects.create(user=self.user, pgn=PGN)  # not analysed
        response = self.client.get(reverse("coaching_home"))
        self.assertEqual(response.context["games"], {"ready": 1, "missing_side": 1, "not_analysed": 1})
        # Only the ready game can be ticked.
        self.assertEqual(list(response.context["ready_games"]), [self.game])
        self.assertContains(response, f'name="games" value="{self.game.pk}"')


class UserColorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.client.login(username="tester", password="pass12345")

    def test_side_is_detected_from_the_username(self):
        self.client.post(reverse("upload_game"), {"pgn": PGN, "played_as": "auto"})
        self.assertEqual(Game.objects.get().user_color, "white")

    def test_side_can_be_chosen_on_upload(self):
        self.client.post(reverse("upload_game"), {"pgn": PGN, "played_as": "black"})
        self.assertEqual(Game.objects.get().user_color, "black")

    def test_side_can_be_set_on_the_game_page(self):
        game = Game.objects.create(user=self.user, pgn=PGN)
        self.client.post(reverse("set_game_color", args=[game.pk]), {"color": "black"})
        game.refresh_from_db()
        self.assertEqual(game.user_color, "black")

    def test_invalid_side_is_rejected(self):
        game = Game.objects.create(user=self.user, pgn=PGN)
        response = self.client.post(reverse("set_game_color", args=[game.pk]), {"color": "purple"}, follow=True)
        self.assertContains(response, "Please choose White or Black")


class DeleteGameTests(CoachingTestBase):
    def test_owner_can_delete_a_game_with_its_analysis(self):
        response = self.client.post(reverse("delete_game", args=[self.game.pk]), follow=True)
        self.assertRedirects(response, reverse("game_list"))
        self.assertFalse(Game.objects.filter(pk=self.game.pk).exists())
        self.assertEqual(Move.objects.count(), 0)
        self.assertContains(response, "Game deleted")

    def test_delete_needs_post_and_ownership(self):
        self.assertEqual(self.client.get(reverse("delete_game", args=[self.game.pk])).status_code, 405)
        User.objects.create_user("intruder", password="pass12345")
        self.client.login(username="intruder", password="pass12345")
        self.assertEqual(self.client.post(reverse("delete_game", args=[self.game.pk])).status_code, 404)
        self.assertTrue(Game.objects.filter(pk=self.game.pk).exists())


@override_settings(TASKS=IMMEDIATE_TASKS, AI_API_KEY="test-key")
class PracticeTests(CoachingTestBase):
    def setUp(self):
        super().setUp()
        llm = fake_llm(final_answer(weakness(self.game.pk)))
        with mock.patch.object(diagnosis_service, "_make_llm", return_value=llm):
            self.client.post(reverse("create_report"), self.choose())
        self.report = WeaknessReport.objects.get()

    def test_tick_and_untick_a_practice_item(self):
        url = reverse("toggle_practice", args=[self.report.pk, 0])
        response = self.client.post(url, {"done": "1"})
        self.assertRedirects(response, reverse("report_detail", args=[self.report.pk]) + "#practice",
                             fetch_redirect_response=False)
        self.assertTrue(TrainingPlan.objects.get().tasks[0]["done"])
        page = self.client.get(reverse("report_detail", args=[self.report.pk]))
        self.assertContains(page, "1 of 1 done")

        self.client.post(url, {"done": "0"})
        self.assertFalse(TrainingPlan.objects.get().tasks[0]["done"])

    def test_unknown_item_or_other_user_gives_404(self):
        self.assertEqual(
            self.client.post(reverse("toggle_practice", args=[self.report.pk, 9]), {"done": "1"}).status_code, 404
        )
        User.objects.create_user("intruder", password="pass12345")
        self.client.login(username="intruder", password="pass12345")
        self.assertEqual(
            self.client.post(reverse("toggle_practice", args=[self.report.pk, 0]), {"done": "1"}).status_code, 404
        )
        self.assertFalse(TrainingPlan.objects.get().tasks[0]["done"])