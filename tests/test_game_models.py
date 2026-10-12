from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.games.models import Game, Mistake, Move
from apps.games.services.pgn_import_service import import_pgn
from tests.test_pgn_import import VALID_PGN


class PgnHeaderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="pass12345")

    def test_headers_are_saved(self):
        game = import_pgn(self.user, VALID_PGN)
        self.assertEqual((game.white, game.black, game.result), ("Alice", "Bob", "1-0"))

    def test_unknown_headers_are_stored_empty(self):
        game = import_pgn(self.user, '[White "?"]\n[Result "*"]\n\n1. e4 e5 *')
        self.assertEqual((game.white, game.black, game.result), ("", "", ""))


class MoveAndMistakeTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("tester", password="pass12345")
        self.game = Game.objects.create(user=user, pgn=VALID_PGN)

    def make_move(self, ply=1, san="e4"):
        return Move.objects.create(
            game=self.game, ply=ply, color=Move.Color.WHITE, san=san, uci="e2e4",
            fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        )

    def test_moves_are_reachable_from_game_in_order(self):
        self.make_move(ply=2, san="e5")
        self.make_move(ply=1, san="e4")
        self.assertEqual([m.san for m in self.game.moves.all()], ["e4", "e5"])

    def test_same_ply_twice_is_rejected(self):
        self.make_move(ply=1)
        with self.assertRaises(IntegrityError):
            self.make_move(ply=1)

    def test_mistake_links_to_its_move(self):
        move = self.make_move()
        Mistake.objects.create(
            move=move, severity=Mistake.Severity.BLUNDER, phase=Mistake.Phase.OPENING
        )
        self.assertEqual(move.mistake.severity, "blunder")
        self.assertEqual(str(move.mistake), "Blunder at 1. e4")

    def test_deleting_game_deletes_moves_and_mistakes(self):
        move = self.make_move()
        Mistake.objects.create(move=move, severity="mistake", phase="opening")
        self.game.delete()
        self.assertEqual(Move.objects.count(), 0)
        self.assertEqual(Mistake.objects.count(), 0)