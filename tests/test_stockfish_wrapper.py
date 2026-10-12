import os
import shutil
import unittest

import chess

from ai.engine import EngineNotFoundError, StockfishEngine

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH") or shutil.which("stockfish") or "/usr/bin/stockfish"
HAS_STOCKFISH = os.path.exists(STOCKFISH_PATH)

# Position just before 4. Qxf7# (Scholar's mate), White to move.
MATE_IN_ONE = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
# Black has been checkmated (after 4. Qxf7#), Black to move.
BLACK_IS_MATED = "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
# Black's queen is missing; otherwise the starting position.
WHITE_QUEEN_UP = "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@unittest.skipUnless(HAS_STOCKFISH, f"Stockfish not installed at {STOCKFISH_PATH}")
class StockfishEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start the engine once for all tests: starting it is the slow part.
        cls.engine = StockfishEngine(STOCKFISH_PATH, depth=10).open()

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def test_starting_position_is_roughly_equal(self):
        result = self.engine.evaluate(chess.Board())
        self.assertLess(abs(result.cp), 100)
        self.assertIsNone(result.mate)
        self.assertIn(result.best_move, chess.Board().legal_moves)

    def test_finds_mate_in_one(self):
        result = self.engine.evaluate(chess.Board(MATE_IN_ONE))
        self.assertEqual(result.best_move, chess.Move.from_uci("h5f7"))
        self.assertEqual(result.mate, 1)
        self.assertGreater(result.cp, 9000)

    def test_mated_position_has_no_best_move(self):
        result = self.engine.evaluate(chess.Board(BLACK_IS_MATED))
        self.assertIsNone(result.best_move)
        self.assertGreater(result.cp, 9000)  # White has won

    def test_material_advantage_is_seen_from_whites_side(self):
        white_to_move = self.engine.evaluate(chess.Board(WHITE_QUEEN_UP))
        board = chess.Board(WHITE_QUEEN_UP)
        board.turn = chess.BLACK
        black_to_move = self.engine.evaluate(board)
        # Positive for White no matter whose turn it is.
        self.assertGreater(white_to_move.cp, 500)
        self.assertGreater(black_to_move.cp, 500)


class StockfishEngineErrorTests(unittest.TestCase):
    def test_wrong_path_gives_clear_error(self):
        with self.assertRaises(EngineNotFoundError):
            StockfishEngine("/no/such/stockfish").open()

    def test_evaluate_without_open_fails(self):
        with self.assertRaises(RuntimeError):
            StockfishEngine(STOCKFISH_PATH).evaluate(chess.Board())