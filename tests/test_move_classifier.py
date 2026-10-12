import unittest

import chess

from ai.engine.move_classifier import (
    BLUNDER, ENDGAME, INACCURACY, MIDDLEGAME, MISTAKE, OPENING,
    Score, centipawn_loss, classify_move, game_phase, winning_chances,
)


class WinningChancesTests(unittest.TestCase):
    def test_equal_position_is_zero(self):
        self.assertEqual(winning_chances(0), 0)

    def test_is_symmetric_and_bounded(self):
        self.assertAlmostEqual(winning_chances(300), -winning_chances(-300))
        self.assertLess(winning_chances(5000), 1)
        self.assertGreater(winning_chances(-5000), -1)


class ClassifyMoveTests(unittest.TestCase):
    def test_small_drop_is_fine(self):
        self.assertIsNone(classify_move(Score(cp=30), Score(cp=10), mover_is_white=True))

    def test_thresholds(self):
        self.assertEqual(classify_move(Score(cp=50), Score(cp=-50), True), INACCURACY)
        self.assertEqual(classify_move(Score(cp=0), Score(cp=-150), True), MISTAKE)
        self.assertEqual(classify_move(Score(cp=0), Score(cp=-300), True), BLUNDER)

    def test_black_moves_are_judged_from_blacks_side(self):
        # +250 is good for White, so this move threw away Black's advantage.
        self.assertEqual(classify_move(Score(cp=-50), Score(cp=250), False), BLUNDER)
        # The same numbers are an improvement if White had played the move.
        self.assertIsNone(classify_move(Score(cp=-50), Score(cp=250), True))

    def test_same_drop_matters_less_when_already_winning(self):
        # 200 centipawns lost at +900 barely changes the winning chances.
        self.assertIsNone(classify_move(Score(cp=900), Score(cp=700), True))

    def test_allowing_mate(self):
        self.assertEqual(classify_move(Score(cp=0), Score(mate=-3), True), BLUNDER)
        self.assertEqual(classify_move(Score(cp=-800), Score(mate=-3), True), MISTAKE)
        self.assertEqual(classify_move(Score(cp=-1200), Score(mate=-3), True), INACCURACY)

    def test_missing_a_forced_mate(self):
        self.assertEqual(classify_move(Score(mate=2), Score(cp=300), True), BLUNDER)
        self.assertEqual(classify_move(Score(mate=2), Score(cp=1500), True), INACCURACY)
        self.assertIsNone(classify_move(Score(mate=2), Score(mate=3), True))


class CentipawnLossTests(unittest.TestCase):
    def test_loss_for_white_and_black(self):
        self.assertEqual(centipawn_loss(Score(cp=50), Score(cp=-30), True), 80)
        self.assertEqual(centipawn_loss(Score(cp=-50), Score(cp=30), False), 80)

    def test_improvement_counts_as_zero(self):
        self.assertEqual(centipawn_loss(Score(cp=0), Score(cp=100), True), 0)

    def test_large_values_are_capped(self):
        self.assertEqual(centipawn_loss(Score(mate=3), Score(cp=-5000), True), 2000)


class GamePhaseTests(unittest.TestCase):
    def test_first_ten_moves_are_opening(self):
        self.assertEqual(game_phase(chess.Board(), ply=1), OPENING)

    def test_full_board_after_move_ten_is_middlegame(self):
        self.assertEqual(game_phase(chess.Board(), ply=30), MIDDLEGAME)

    def test_rooks_and_pawns_only_is_endgame(self):
        board = chess.Board("r5k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 40")
        self.assertEqual(game_phase(board, ply=79), ENDGAME)

    def test_queen_and_rook_is_not_endgame(self):
        board = chess.Board("r2q2k1/5ppp/8/8/8/8/5PPP/R2Q2K1 w - - 0 40")
        self.assertEqual(game_phase(board, ply=79), MIDDLEGAME)