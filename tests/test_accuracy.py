import unittest

from ai.engine.accuracy import game_accuracy, move_accuracy, win_percent


class WinPercentTests(unittest.TestCase):
    def test_equal_is_fifty_percent(self):
        self.assertAlmostEqual(win_percent(0), 50)

    def test_evaluations_are_capped_at_ten_pawns(self):
        self.assertEqual(win_percent(10_000), win_percent(1000))
        self.assertGreater(win_percent(1000), 95)


class MoveAccuracyTests(unittest.TestCase):
    def test_no_loss_is_100(self):
        self.assertEqual(move_accuracy(50, 50), 100)
        self.assertEqual(move_accuracy(50, 60), 100)

    def test_lichess_formula(self):
        # 103.1668 * exp(-0.04354 * 10) - 3.1669 + 1 = 64.6 for a 10% drop.
        self.assertAlmostEqual(move_accuracy(60, 50), 64.58, places=1)

    def test_huge_loss_is_0(self):
        self.assertEqual(move_accuracy(100, 0), 0)


class GameAccuracyTests(unittest.TestCase):
    def test_perfect_game_is_100_for_both(self):
        self.assertEqual(game_accuracy(20, [20, 20, 20, 20]), {"white": 100.0, "black": 100.0})

    def test_blunder_lowers_only_the_blunderers_accuracy(self):
        # Black's second move drops from equal to -5 pawns.
        accuracy = game_accuracy(20, [20, 20, 20, 500, 500, 500])
        self.assertEqual(accuracy["white"], 100.0)
        self.assertLess(accuracy["black"], 60)

    def test_one_move_game(self):
        self.assertEqual(game_accuracy(20, [20]), {"white": 100.0, "black": None})
