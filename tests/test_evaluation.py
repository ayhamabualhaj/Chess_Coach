import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

import chess.pgn
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from ai.engine import StockfishEngine
from evaluation.measure_accuracy import compare, has_lichess_analysis, lichess_labels, scores
from evaluation.measure_latency import stopwatch
from evaluation.measure_memory import python_memory
from evaluation.run_evaluation import evaluate_game, format_summary, read_games, summarize
from tests.test_stockfish_wrapper import HAS_STOCKFISH, STOCKFISH_PATH

# Written like a Lichess export "with computer analysis": [%eval] comments, a glyph
# after each judged move and a comment saying why. 2.Qh5?! has only the comment.
LICHESS_GAME = """[Event "Rated blitz game"]
[Site "https://lichess.org/AbCdEfGh"]
[White "tester"]
[Black "rival"]
[Result "1-0"]

1. e4 { [%eval 0.25] } 1... e5 { [%eval 0.3] } 2. Qh5 { [%eval -0.2] } { Inaccuracy. Nf3 was best. }
2... Nc6 { [%eval -0.1] } 3. Bc4 { [%eval -0.2] } 3... Nf6?? { [%eval #1] } { (-0.20 → Mate in 1) Checkmate is now unavoidable. g6 was best. }
(3... g6 4. Qf3 Nf6) 4. Qxf7# { White wins by checkmate. } 1-0
"""
PLAIN_GAME = '[White "a"]\n[Black "b"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n'


def parse(text):
    return chess.pgn.read_game(io.StringIO(text))


class LichessLabelTests(unittest.TestCase):
    def test_glyphs_and_comments_are_read(self):
        self.assertEqual(lichess_labels(parse(LICHESS_GAME)), {3: "inaccuracy", 6: "blunder"})

    def test_games_without_analysis_are_recognised(self):
        self.assertTrue(has_lichess_analysis(parse(LICHESS_GAME)))
        self.assertFalse(has_lichess_analysis(parse(PLAIN_GAME)))


class CompareTests(unittest.TestCase):
    def test_counts_scores_and_confusion(self):
        ours = {6: "blunder", 9: "mistake"}
        theirs = {3: "inaccuracy", 6: "blunder"}
        result = compare(ours, theirs, plies=10)
        self.assertEqual((result["true_pos"], result["false_pos"], result["false_neg"]), (1, 1, 1))
        self.assertEqual((result["precision"], result["recall"], result["f1"]), (0.5, 0.5, 0.5))
        self.assertEqual(result["same_severity"], 1)
        self.assertEqual(result["confusion"]["inaccuracy"]["none"], 1)
        self.assertEqual(result["confusion"]["none"]["none"], 7)

    def test_undefined_scores_are_none(self):
        self.assertEqual(scores(0, 0, 0), {"precision": None, "recall": None, "f1": None})


class MeasureTests(unittest.TestCase):
    def test_stopwatch_and_memory(self):
        with python_memory() as memory, stopwatch() as watch:
            data = [0] * 200_000
        self.assertGreaterEqual(watch["seconds"], 0)
        self.assertGreater(memory["peak_mb"], 1)  # the list above takes about 1.5 MB
        del data

    def test_engine_memory_is_none_when_not_running(self):
        self.assertIsNone(StockfishEngine("/no/such/stockfish").peak_memory_mb())


class ReadAndSummarizeTests(unittest.TestCase):
    def test_only_analysed_games_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "games.pgn"
            path.write_text(PLAIN_GAME + "\n" + LICHESS_GAME)
            games, skipped = read_games([path])
        self.assertEqual((len(games), skipped), (1, 1))

    def test_summary_adds_up_games_per_depth(self):
        confusion = compare({6: "blunder"}, {6: "blunder"}, plies=7)["confusion"]
        row = {"depth": 12, "plies": 7, "seconds": 1.0, "ms_per_move": 143, "python_peak_mb": 0.5,
               "engine_peak_mb": 150.0, "great_overhead_pct": None, "lichess_labels": 1, "our_labels": 1,
               "true_pos": 1, "false_pos": 0, "false_neg": 0, "same_severity": 1, "confusion": confusion}
        summary = summarize([row, {**row, "seconds": 3.0}])
        self.assertEqual((summary[0]["games"], summary[0]["total_seconds"], summary[0]["f1"]), (2, 4.0, 1.0))
        self.assertIn("Depth 12: 2 games, 14 moves", format_summary(summary))


@unittest.skipUnless(HAS_STOCKFISH, "Stockfish not installed")
@override_settings(STOCKFISH_PATH=STOCKFISH_PATH)
class EvaluateWithStockfishTests(SimpleTestCase):
    def test_one_game_gives_a_full_row(self):
        row = evaluate_game(parse(LICHESS_GAME), 1, depth=8, great_overhead=True)
        self.assertEqual((row["game"], row["plies"], row["depth"]), ("AbCdEfGh", 7, 8))
        self.assertGreater(row["seconds"], 0)
        self.assertIsNotNone(row["seconds_without_great"])
        self.assertGreaterEqual(row["true_pos"], 1)  # 3...Nf6?? is found by both
        if sys.platform.startswith("linux"):
            self.assertGreater(row["engine_peak_mb"], 0)

    def test_command_writes_csv_and_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            pgn = Path(folder) / "games.pgn"
            pgn.write_text(LICHESS_GAME)
            out = Path(folder) / "results.csv"
            call_command("evaluate", str(pgn), "--depths", "6", "8", "--out", str(out), stdout=io.StringIO())
            with open(out, newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["depth"] for row in rows], ["6", "8"])
            self.assertIn("Accuracy: precision", out.with_suffix(".txt").read_text())


class CommandErrorTests(SimpleTestCase):
    def test_missing_file_and_unanalysed_games(self):
        with self.assertRaisesMessage(CommandError, "File not found"):
            call_command("evaluate", "/no/such.pgn", stdout=io.StringIO())
        with tempfile.TemporaryDirectory() as folder:
            pgn = Path(folder) / "plain.pgn"
            pgn.write_text(PLAIN_GAME)
            with self.assertRaisesMessage(CommandError, "No games with Lichess computer analysis"):
                call_command("evaluate", str(pgn), stdout=io.StringIO())
