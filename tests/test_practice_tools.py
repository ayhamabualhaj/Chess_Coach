import unittest

from ai.tools.practice_tools import build_practice
from ai.tools.stats_tools import MoveRecord

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def record(game_id, ply, san, cp_loss, severity="", motif="", phase="middlegame"):
    return MoveRecord(game_id=game_id, ply=ply, san=san, fen_before=FEN, phase=phase,
                      cp_loss=cp_loss, severity=severity, motif=motif)


class BuildPracticeTests(unittest.TestCase):
    def test_three_puzzles_per_mistake_of_each_type(self):
        items = build_practice([
            record(1, 20, "cxb5", 89, "mistake", "missed_fork"),
            record(2, 33, "Nf3", 300, "blunder", "missed_fork"),
            record(1, 11, "Qxf7+", 276, "blunder", "hanging_piece"),
        ])
        by_theme = {item["theme"]: item for item in items}
        self.assertEqual(by_theme["fork"]["puzzles"], 6)
        self.assertEqual(by_theme["hangingPiece"]["puzzles"], 3)
        self.assertEqual(by_theme["fork"]["url"], "https://lichess.org/training/fork")

    def test_most_common_mistake_type_comes_first_and_examples_link_to_games(self):
        items = build_practice([
            record(1, 11, "Qxf7+", 276, "blunder", "hanging_piece"),
            record(2, 20, "cxb5", 89, "mistake", "missed_fork"),
            record(3, 33, "Nf3", 300, "blunder", "missed_fork"),
        ])
        self.assertEqual(items[0]["theme"], "fork")
        # Worst example first, with its game id.
        self.assertEqual(items[0]["examples"][0], {"move": "17. Nf3", "game_id": 3})
        self.assertEqual(items[0]["examples"][1], {"move": "10... cxb5", "game_id": 2})

    def test_mistakes_without_a_motif_are_trained_by_phase(self):
        items = build_practice([record(1, 70, "Kd2", 150, "mistake", "", phase="endgame")])
        self.assertEqual((items[0]["theme"], items[0]["name"]), ("endgame", "Endgame"))

    def test_good_moves_give_no_practice_and_counts_are_capped(self):
        self.assertEqual(build_practice([record(1, 1, "e4", 0)]), [])
        many = [record(1, ply, "Qh5", 300, "blunder", "hanging_piece") for ply in range(1, 20)]
        self.assertEqual(build_practice(many)[0]["puzzles"], 15)

    def test_items_start_not_done(self):
        items = build_practice([record(1, 11, "Qxf7+", 276, "blunder", "hanging_piece")])
        self.assertFalse(items[0]["done"])