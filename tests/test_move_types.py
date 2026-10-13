import unittest

import chess
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from ai.engine import Score
from ai.engine.move_types import (
    BEST, BRILLIANT, EXCELLENT, GOOD, GREAT, MISS,
    expected_points, is_sacrifice, move_type, should_check_great,
)
from ai.tools.stats_tools import MoveRecord, summarize_mistakes
from apps.games.models import Game, Move
from apps.games.services.analysis_service import analyse_game
from tests.test_stockfish_wrapper import HAS_STOCKFISH, STOCKFISH_PATH

EQUAL = Score(cp=0)


class ExpectedPointsTests(unittest.TestCase):
    def test_equal_position_is_half_a_point(self):
        self.assertAlmostEqual(expected_points(EQUAL, True), 0.5)

    def test_points_are_seen_from_the_movers_side(self):
        white_better = Score(cp=300)
        self.assertGreater(expected_points(white_better, True), 0.7)
        self.assertLess(expected_points(white_better, False), 0.3)

    def test_mate_counts_as_winning(self):
        self.assertGreater(expected_points(Score(mate=3), True), 0.95)


class MoveTypeTests(unittest.TestCase):
    def test_engine_move_is_best(self):
        self.assertEqual(move_type(EQUAL, EQUAL, True, played_best=True), BEST)

    def test_small_losses_are_excellent_then_good(self):
        # 10 cp from equal loses about 0.01 expected points, 50 cp about 0.05.
        self.assertEqual(move_type(EQUAL, Score(cp=-10), True, played_best=False), EXCELLENT)
        self.assertEqual(move_type(EQUAL, Score(cp=-45), True, played_best=False), GOOD)

    def test_lichess_label_is_kept_for_bad_moves(self):
        self.assertEqual(move_type(EQUAL, Score(cp=-300), True, False, severity="blunder"), "blunder")

    def test_not_punishing_a_mistake_is_a_miss(self):
        kind = move_type(Score(cp=300), Score(cp=50), True, False, severity="mistake", opponent_severity="blunder")
        self.assertEqual(kind, MISS)

    def test_after_an_inaccuracy_it_is_not_a_miss(self):
        kind = move_type(Score(cp=100), Score(cp=-50), True, False, severity="inaccuracy", opponent_severity="inaccuracy")
        self.assertEqual(kind, "inaccuracy")

    def test_only_good_move_is_great(self):
        second_best = Score(cp=-300)  # every other move loses badly
        self.assertEqual(move_type(EQUAL, EQUAL, True, True, second_best=second_best), GREAT)
        self.assertEqual(move_type(EQUAL, EQUAL, True, True, second_best=Score(cp=-20)), BEST)

    def test_good_sacrifice_is_brilliant(self):
        self.assertEqual(move_type(EQUAL, Score(cp=20), True, True, sacrifice=True), BRILLIANT)

    def test_sacrifice_that_loses_or_when_already_winning_is_not_brilliant(self):
        self.assertNotEqual(move_type(EQUAL, Score(cp=-150), True, False, sacrifice=True), BRILLIANT)
        self.assertNotEqual(move_type(Score(cp=900), Score(cp=900), True, True, sacrifice=True), BRILLIANT)


class SacrificeTests(unittest.TestCase):
    def test_piece_left_where_a_pawn_can_take_it(self):
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        self.assertTrue(is_sacrifice(board, chess.Move.from_uci("f1a6")))  # b7 pawn takes the bishop

    def test_safe_square_is_not_a_sacrifice(self):
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        self.assertFalse(is_sacrifice(board, chess.Move.from_uci("f1c4")))

    def test_fair_trade_is_not_a_sacrifice(self):
        # Bxc6 bxc6: bishop for knight.
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4")
        self.assertFalse(is_sacrifice(board, chess.Move.from_uci("b5c6")))

    def test_pawn_moves_are_never_sacrifices(self):
        board = chess.Board()
        self.assertFalse(is_sacrifice(board, chess.Move.from_uci("e2e4")))


class GreatCheckTests(unittest.TestCase):
    MIDDLEGAME = "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"

    def test_only_the_best_move_is_checked(self):
        board = chess.Board(self.MIDDLEGAME)
        move = chess.Move.from_uci("c1g5")
        self.assertTrue(should_check_great(board, move, EQUAL, played_best=True, ply=13))
        self.assertFalse(should_check_great(board, move, EQUAL, played_best=False, ply=13))

    def test_opening_moves_and_decided_games_are_skipped(self):
        board = chess.Board(self.MIDDLEGAME)
        move = chess.Move.from_uci("c1g5")
        self.assertFalse(should_check_great(board, move, EQUAL, played_best=True, ply=5))
        self.assertFalse(should_check_great(board, move, Score(cp=900), played_best=True, ply=13))

    def test_obvious_moves_are_skipped(self):
        # Getting out of check.
        in_check = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/4P2q/5P2/PPPP2PP/RNBQKBNR w KQkq - 1 3")
        self.assertFalse(should_check_great(in_check, chess.Move.from_uci("g2g3"), EQUAL, True, 13))
        # Taking back a piece that was just captured.
        board = chess.Board("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4")
        board.push_uci("b5c6")
        self.assertFalse(should_check_great(board, chess.Move.from_uci("d7c6"), EQUAL, True, 13))


class CoachSeesMoveTypesTests(unittest.TestCase):
    def test_summary_counts_good_moves_too(self):
        fen = chess.STARTING_FEN
        records = [
            MoveRecord(game_id=1, ply=1, san="e4", fen_before=fen, phase="opening", cp_loss=0, label="best"),
            MoveRecord(game_id=1, ply=3, san="Nf3", fen_before=fen, phase="opening", cp_loss=0, label="great"),
        ]
        types = summarize_mistakes(records)["move_types"]
        self.assertEqual((types["best"], types["great"], types["blunder"]), (1, 1, 0))


@override_settings(STOCKFISH_PATH=STOCKFISH_PATH)
class AnalysisSavesMoveTypesTests(TestCase):
    def setUp(self):
        if not HAS_STOCKFISH:
            self.skipTest("Stockfish not installed")
        user = get_user_model().objects.create_user("tester", password="pass12345")
        self.game = Game.objects.create(user=user, pgn="1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0")

    def test_every_move_gets_a_type(self):
        analyse_game(self.game.pk, depth=10)
        labels = list(Move.objects.filter(game=self.game).order_by("ply").values_list("label", flat=True))
        self.assertTrue(all(labels))
        self.assertEqual(labels[5], "blunder")  # 3...Nf6?? allows mate
        self.assertEqual(labels[6], "best")  # 4.Qxf7#
