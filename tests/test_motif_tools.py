import unittest

import chess

from ai.tools.motif_tools import (
    ALLOWED_FORCED_MATE, ALLOWED_MATE, HANGING_PIECE, MISSED_FORCED_MATE,
    MISSED_CAPTURE, MISSED_CHECK, MISSED_FORK, MISSED_MATE,
    detect_motifs, engine_mate_motif, primary_motif,
)


def fen_after(san_moves: str) -> str:
    board = chess.Board()
    for san in san_moves.split():
        board.push_san(san)
    return board.fen()


class MotifTests(unittest.TestCase):
    def test_allowing_mate_in_one(self):
        # 1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6?? allows 4. Qxf7#
        fen = fen_after("e4 e5 Qh5 Nc6 Bc4")
        self.assertEqual(primary_motif(fen, "g8f6", "g7g6"), ALLOWED_MATE)

    def test_missing_mate_in_one(self):
        fen = fen_after("e4 e5 Qh5 Nc6 Bc4 Nf6")
        self.assertEqual(primary_motif(fen, "d2d3", "h5f7"), MISSED_MATE)

    def test_hanging_piece(self):
        # 1. e4 d5 2. Qg4?? and the bishop on c8 takes the queen.
        fen = fen_after("e4 d5")
        self.assertEqual(detect_motifs(fen, "d1g4", "e4d5"), [HANGING_PIECE])

    def test_missed_capture(self):
        fen = fen_after("e4 d5 Qg4")
        self.assertEqual(detect_motifs(fen, "g8f6", "c8g4"), [MISSED_CAPTURE])

    def test_missed_knight_fork(self):
        # Nc7+ attacks the king on e8 and the rook on a8.
        fen = "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1"
        self.assertEqual(detect_motifs(fen, "e1e2", "b5c7"), [MISSED_FORK, MISSED_CHECK])

    def test_fair_trade_is_not_a_hanging_piece(self):
        # 4. Bxc6 gives the bishop for a knight: an equal trade, not a blunder pattern.
        fen = fen_after("e4 e5 Nf3 Nc6 Bb5 a6")
        self.assertNotIn(HANGING_PIECE, detect_motifs(fen, "b5c6", "b5a4"))

    def test_quiet_move_has_no_motif(self):
        self.assertEqual(primary_motif(chess.STARTING_FEN, "e2e4", "d2d4"), "")


class EngineMateMotifTests(unittest.TestCase):
    def test_allowing_a_forced_mate(self):
        # Before: no mate. After Black's move: White mates in 2 (+2 from White's side).
        self.assertEqual(engine_mate_motif(None, 2, mover_is_white=False), ALLOWED_FORCED_MATE)

    def test_missing_a_forced_mate(self):
        self.assertEqual(engine_mate_motif(3, None, mover_is_white=True), MISSED_FORCED_MATE)

    def test_keeping_the_mate_is_fine(self):
        self.assertEqual(engine_mate_motif(3, 2, mover_is_white=True), "")