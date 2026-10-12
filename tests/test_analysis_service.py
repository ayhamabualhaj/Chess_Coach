from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.engine import EngineNotFoundError
from ai.engine.stockfish_wrapper import MATE_SCORE
from apps.games.models import Game, Mistake, Move
from apps.games.services.analysis_service import analyse_game
from tests.test_stockfish_wrapper import HAS_STOCKFISH, STOCKFISH_PATH

# 3...Nf6?? lets White mate with 4. Qxf7#.
BLUNDER_GAME = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


class AnalysisServiceTestBase(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("tester", password="pass12345")
        self.game = Game.objects.create(user=user, pgn=BLUNDER_GAME)


@override_settings(STOCKFISH_PATH=STOCKFISH_PATH)
class AnalyseGameTests(AnalysisServiceTestBase):
    def setUp(self):
        if not HAS_STOCKFISH:
            self.skipTest("Stockfish not installed")
        super().setUp()

    def test_every_move_is_stored_with_evaluations(self):
        summary = analyse_game(self.game.pk, depth=10)
        self.assertEqual(summary["moves"], 7)
        moves = list(self.game.moves.all())
        self.assertEqual([m.san for m in moves], ["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"])
        self.assertTrue(all(m.eval_before is not None and m.cp_loss is not None for m in moves))
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.DONE)

    def test_blunder_allowing_mate_is_found(self):
        analyse_game(self.game.pk, depth=10)
        nf6 = Move.objects.get(game=self.game, ply=6)
        self.assertEqual(nf6.color, "black")
        self.assertEqual(nf6.mistake.severity, Mistake.Severity.BLUNDER)
        self.assertEqual(nf6.mistake.phase, Mistake.Phase.OPENING)

    def test_mating_move_is_not_a_mistake(self):
        analyse_game(self.game.pk, depth=10)
        mate = Move.objects.get(game=self.game, ply=7)
        self.assertEqual(mate.eval_after, MATE_SCORE)
        self.assertEqual(mate.cp_loss, 0)
        self.assertFalse(Mistake.objects.filter(move=mate).exists())

    def test_running_twice_does_not_duplicate(self):
        analyse_game(self.game.pk, depth=10)
        analyse_game(self.game.pk, depth=10)
        self.assertEqual(Move.objects.filter(game=self.game).count(), 7)


@override_settings(STOCKFISH_PATH="/no/such/stockfish")
class AnalyseGameFailureTests(AnalysisServiceTestBase):
    def test_missing_engine_marks_game_failed(self):
        with self.assertRaises(EngineNotFoundError):
            analyse_game(self.game.pk)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, Game.Status.FAILED)
        self.assertEqual(Move.objects.count(), 0)