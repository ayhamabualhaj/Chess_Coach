import unittest

from ai.tools.stats_tools import MoveRecord, opening_breakdown, opening_label, summarize_mistakes, worst_moves

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def record(game_id, ply, phase, cp_loss, severity="", motif="", opening="Sicilian Defense"):
    return MoveRecord(
        game_id=game_id, ply=ply, san="e4", fen_before=FEN, phase=phase,
        cp_loss=cp_loss, severity=severity, motif=motif, opening=opening,
    )


RECORDS = [
    record(1, 1, "opening", 10),
    record(1, 3, "opening", 120, "mistake", "missed_capture"),
    record(1, 41, "middlegame", 400, "blunder", "hanging_piece"),
    record(1, 43, "middlegame", 0),
    record(2, 2, "opening", 20, opening="French Defense"),
    record(2, 60, "endgame", 250, "blunder", "hanging_piece", opening="French Defense"),
]


class SummarizeMistakesTests(unittest.TestCase):
    def setUp(self):
        self.summary = summarize_mistakes(RECORDS)

    def test_totals(self):
        self.assertEqual(self.summary["games"], 2)
        self.assertEqual(self.summary["moves"], 6)
        self.assertEqual(self.summary["by_severity"], {"inaccuracy": 0, "mistake": 1, "blunder": 2})

    def test_by_phase(self):
        middlegame = self.summary["by_phase"]["middlegame"]
        self.assertEqual(middlegame["moves"], 2)
        self.assertEqual(middlegame["mistakes_per_100_moves"], 50.0)
        self.assertEqual(middlegame["avg_cp_loss"], 200.0)

    def test_motifs_most_common_first(self):
        self.assertEqual(list(self.summary["by_motif"].items())[0], ("hanging_piece", 2))

    def test_empty_input(self):
        empty = summarize_mistakes([])
        self.assertEqual(empty["moves"], 0)
        self.assertIsNone(empty["avg_cp_loss"])


class OpeningAndEvidenceTests(unittest.TestCase):
    def test_opening_breakdown_worst_first(self):
        rows = opening_breakdown(RECORDS)
        # French: (20 + 250) / 2 = 135 cp; Sicilian: (10 + 120 + 400 + 0) / 4 = 132.5 cp
        self.assertEqual([r["opening"] for r in rows], ["French Defense", "Sicilian Defense"])
        self.assertEqual(rows[1]["opening_phase_mistakes"], 1)

    def test_worst_moves_are_sorted_and_filtered(self):
        worst = worst_moves(RECORDS, limit=2)
        self.assertEqual([w["cp_loss"] for w in worst], [400, 250])
        self.assertEqual(worst[0]["move"], "21. e4")
        endgame = worst_moves(RECORDS, phase="endgame")
        self.assertEqual(len(endgame), 1)
        self.assertEqual(endgame[0]["move"], "30... e4")

    def test_opening_label(self):
        self.assertEqual(opening_label({"Opening": "Italian Game"}, []), "Italian Game")
        self.assertEqual(opening_label({"ECO": "C50"}, []), "ECO C50")
        self.assertEqual(opening_label({}, ["e4", "e5", "Nf3"]), "1. e4 e5 2. Nf3")