"""The JSON API (Django REST Framework): authentication, serializers and permissions."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.coaching.models import TrainingPlan, WeaknessReport
from apps.games.models import Game, Mistake, Move
from tests.test_game_pages import AFTER_E4_FEN, DUMMY_TASKS, START_FEN

User = get_user_model()
PGN = "1. e4 f6 *"


class ApiTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.token = Token.objects.create(user=self.user)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.game = Game.objects.create(
            user=self.user, pgn=PGN, white="tester", black="rival", result="1-0",
            user_color="white", status=Game.Status.DONE,
        )
        Move.objects.create(game=self.game, ply=1, color="white", san="e4", uci="e2e4", fen_before=START_FEN,
                            eval_before=20, eval_after=20, best_move_uci="e2e4", cp_loss=0, label="best")
        f6 = Move.objects.create(game=self.game, ply=2, color="black", san="f6", uci="f7f6", fen_before=AFTER_E4_FEN,
                                 eval_before=20, eval_after=160, best_move_uci="e7e5", cp_loss=140, label="mistake")
        Mistake.objects.create(move=f6, severity="mistake", phase="opening", motif="")


class AuthenticationTests(ApiTestBase):
    def test_token_is_given_for_username_and_password(self):
        response = APIClient().post(reverse("api_token"), {"username": "tester", "password": "pass12345"})
        self.assertEqual(response.json(), {"token": self.token.key})

    def test_requests_without_login_are_refused(self):
        response = APIClient().get(reverse("api_game_list"))
        self.assertEqual(response.status_code, 401)

    def test_browser_session_also_works(self):
        client = APIClient()
        client.login(username="tester", password="pass12345")
        self.assertEqual(client.get(reverse("api_game_list")).status_code, 200)


class GameApiTests(ApiTestBase):
    def test_list_shows_only_own_games_with_pagination(self):
        other = User.objects.create_user("other", password="pass12345")
        Game.objects.create(user=other, pgn=PGN)
        data = self.api.get(reverse("api_game_list")).json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["white"], "tester")
        self.assertEqual(data["results"][0]["user_outcome"], "win")

    def test_filter(self):
        Game.objects.create(user=self.user, pgn=PGN)  # not analysed
        data = self.api.get(reverse("api_game_list"), {"show": "todo"}).json()
        self.assertEqual(data["count"], 1)

    def test_detail_has_moves_labels_and_accuracy(self):
        data = self.api.get(reverse("api_game_detail", args=[self.game.pk])).json()
        self.assertEqual([m["san"] for m in data["moves"]], ["e4", "f6"])
        self.assertEqual((data["moves"][0]["label"], data["moves"][0]["severity"]), ("best", None))
        self.assertEqual(data["moves"][1]["severity"], "mistake")
        self.assertEqual(data["accuracy"]["white"], 100.0)

    def test_someone_elses_game_is_not_found(self):
        other = User.objects.create_user("other", password="pass12345")
        foreign = Game.objects.create(user=other, pgn=PGN)
        self.assertEqual(self.api.get(reverse("api_game_detail", args=[foreign.pk])).status_code, 404)

    @override_settings(TASKS=DUMMY_TASKS, MAX_ANALYSIS_QUEUE=1)
    def test_analyse_queues_then_conflict_then_queue_full(self):
        second = Game.objects.create(user=self.user, pgn=PGN)
        first = self.api.post(reverse("api_analyse_game", args=[self.game.pk]))
        self.assertEqual((first.status_code, first.json()["status"]), (202, "queued"))
        self.assertEqual(self.api.post(reverse("api_analyse_game", args=[self.game.pk])).status_code, 409)
        self.assertEqual(self.api.post(reverse("api_analyse_game", args=[second.pk])).status_code, 429)


class StatusEndpointTests(ApiTestBase):
    """The pages poll these; they are now DRF views with serializers."""

    def test_game_and_queue_status(self):
        self.assertEqual(self.api.get(reverse("game_status", args=[self.game.pk])).json(),
                         {"status": "done", "label": "Analysed"})
        self.assertEqual(self.api.get(reverse("queue_status")).json(), {"in_progress": 0})

    def test_status_needs_login(self):
        self.assertEqual(APIClient().get(reverse("queue_status")).status_code, 401)


@override_settings(TASKS=DUMMY_TASKS, AI_API_KEY="test-key")
class ReportApiTests(ApiTestBase):
    def test_create_list_and_detail(self):
        created = self.api.post(reverse("api_report_list"), {"games": [self.game.pk]}, format="json")
        self.assertEqual(created.status_code, 202)
        report = WeaknessReport.objects.get()
        TrainingPlan.objects.create(report=report, tasks=[{"theme": "fork", "puzzles": 3, "done": False}])

        listed = self.api.get(reverse("api_report_list")).json()
        self.assertEqual(listed["results"][0]["games"], [self.game.pk])
        detail = self.api.get(reverse("api_report_detail", args=[report.pk])).json()
        self.assertEqual((detail["status"], detail["practice"][0]["theme"]), ("queued", "fork"))
        status = self.api.get(reverse("report_status", args=[report.pk])).json()
        self.assertEqual(status, {"status": "queued", "label": "Waiting"})

    def test_serializer_rejects_bad_input(self):
        response = self.api.post(reverse("api_report_list"), {"games": []}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("games", response.json())

    def test_service_rules_are_reported(self):
        self.game.user_color = ""
        self.game.save()
        response = self.api.post(reverse("api_report_list"), {"games": [self.game.pk]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not ready", response.json()["detail"])

    def test_someone_elses_report_is_not_found(self):
        other = User.objects.create_user("other", password="pass12345")
        report = WeaknessReport.objects.create(user=other)
        self.assertEqual(self.api.get(reverse("api_report_detail", args=[report.pk])).status_code, 404)