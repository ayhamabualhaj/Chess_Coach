from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.games.models import Game, Mistake, Move
from apps.games.services import game_service
from tests.test_analysis_service import BLUNDER_GAME
from tests.test_stockfish_wrapper import HAS_STOCKFISH, STOCKFISH_PATH

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

User = get_user_model()


class GamePageTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="pass12345")
        self.game = Game.objects.create(user=self.user, pgn=BLUNDER_GAME, white="A", black="B")
        self.client.login(username="tester", password="pass12345")

    def add_analysed_moves(self):
        """Store a tiny fake analysis: 1. e4 (fine) 1... f6 (a mistake)."""
        Move.objects.create(
            game=self.game, ply=1, color="white", san="e4", uci="e2e4", fen_before=START_FEN,
            eval_before=30, eval_after=35, best_move_uci="e2e4", cp_loss=0,
        )
        f6 = Move.objects.create(
            game=self.game, ply=2, color="black", san="f6", uci="f7f6", fen_before=AFTER_E4_FEN,
            eval_before=35, eval_after=180, best_move_uci="e7e5", cp_loss=145,
        )
        Mistake.objects.create(move=f6, severity="mistake", phase="opening")


class GameDetailTests(GamePageTestBase):
    def test_owner_sees_the_page(self):
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A vs B")
        self.assertContains(response, "not been analysed yet")

    def test_other_users_get_404(self):
        User.objects.create_user("intruder", password="pass12345")
        self.client.login(username="intruder", password="pass12345")
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertEqual(response.status_code, 404)

    def test_list_links_to_detail(self):
        response = self.client.get(reverse("game_list"))
        self.assertContains(response, reverse("game_detail", args=[self.game.pk]))

    def test_analysed_game_shows_moves_mistakes_and_chart(self):
        self.add_analysed_moves()
        response = self.client.get(reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, "Mistake")
        self.assertContains(response, "best was <strong>e5</strong>", html=False)
        self.assertContains(response, 'id="chart-data"')


class GameDetailServiceTests(GamePageTestBase):
    def test_rows_pair_white_and_black_moves(self):
        self.add_analysed_moves()
        detail = game_service.get_game_detail(self.user, self.game.pk)
        row = detail["rows"][0]
        self.assertEqual((row["number"], row["white"]["san"], row["black"]["san"]), (1, "e4", "f6"))
        self.assertEqual(row["black"]["best_san"], "e5")

    def test_stats_per_side(self):
        self.add_analysed_moves()
        stats = game_service.get_game_detail(self.user, self.game.pk)["stats"]
        self.assertEqual(stats["white"]["avg_cp_loss"], 0)
        self.assertEqual(stats["black"]["avg_cp_loss"], 145)
        self.assertEqual(stats["black"]["mistake"], 1)

    def test_chart_starts_at_start_position_and_is_in_pawns(self):
        self.add_analysed_moves()
        chart = game_service.get_game_detail(self.user, self.game.pk)["chart"]
        self.assertEqual(chart["labels"], ["Start", "1. e4", "1... f6"])
        self.assertEqual(chart["evals"], [0.3, 0.35, 1.8])

    def test_mate_scores_are_clipped_in_chart(self):
        Move.objects.create(
            game=self.game, ply=1, color="white", san="e4", uci="e2e4", fen_before=START_FEN,
            eval_before=30, eval_after=10000, cp_loss=0,
        )
        chart = game_service.get_game_detail(self.user, self.game.pk)["chart"]
        self.assertEqual(chart["evals"][-1], 10)


class AnalyseViewTests(GamePageTestBase):
    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("analyse_game", args=[self.game.pk]))
        self.assertEqual(response.status_code, 405)

    def test_cannot_analyse_someone_elses_game(self):
        User.objects.create_user("intruder", password="pass12345")
        self.client.login(username="intruder", password="pass12345")
        response = self.client.post(reverse("analyse_game", args=[self.game.pk]))
        self.assertEqual(response.status_code, 404)

    @override_settings(STOCKFISH_PATH="/no/such/stockfish")
    def test_missing_engine_shows_error_message(self):
        response = self.client.post(reverse("analyse_game", args=[self.game.pk]), follow=True)
        self.assertContains(response, "chess engine is not available")

    @override_settings(STOCKFISH_PATH=STOCKFISH_PATH, STOCKFISH_DEPTH=8)
    def test_analyse_button_runs_analysis(self):
        if not HAS_STOCKFISH:
            self.skipTest("Stockfish not installed")
        response = self.client.post(reverse("analyse_game", args=[self.game.pk]), follow=True)
        self.assertRedirects(response, reverse("game_detail", args=[self.game.pk]))
        self.assertContains(response, "Analysed 7 moves")
        self.assertContains(response, "Blunder")
