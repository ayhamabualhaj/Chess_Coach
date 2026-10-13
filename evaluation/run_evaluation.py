"""Runs the performance evaluation: accuracy, latency and memory per test case.

A test case is one game from a PGN file exported from Lichess with computer
analysis. For each game and each search depth we run our own analysis (the same
code the web app uses), time it, measure its memory, and compare our labels with
Lichess's. Started with:  python manage.py evaluate <file.pgn> ...

Time and memory are measured in separate runs, because tracking every memory
allocation (tracemalloc) slows Python down by roughly 15% in our tests.
"""
import csv
import io
import statistics
from pathlib import Path

import chess
import chess.pgn
from django.conf import settings

from ai.engine import StockfishEngine
from apps.games.services.analysis_service import evaluate_moves
from evaluation.measure_accuracy import SEVERITIES, compare, has_lichess_analysis, lichess_labels, scores
from evaluation.measure_latency import stopwatch
from evaluation.measure_memory import python_memory

CSV_COLUMNS = [
    "game", "white", "black", "result", "plies", "depth",
    "seconds", "repeats", "ms_per_move", "python_peak_mb", "engine_peak_mb", "great_checks",
    "seconds_without_great", "great_overhead_pct",
    "lichess_labels", "our_labels", "true_pos", "false_pos", "false_neg",
    "precision", "recall", "f1", "same_severity",
]


def read_games(paths) -> tuple[list[chess.pgn.Game], int]:
    """(games with Lichess analysis, number of games skipped) from the given PGN files."""
    games, skipped = [], 0
    for path in paths:
        stream = io.StringIO(Path(path).read_text(encoding="utf-8", errors="replace"))
        while (game := chess.pgn.read_game(stream)) is not None:
            if list(game.mainline_moves()) and not game.errors and has_lichess_analysis(game):
                games.append(game)
            else:
                skipped += 1
    return games, skipped


def _name(game: chess.pgn.Game, number: int) -> str:
    site = game.headers.get("Site", "")
    return site.rsplit("/", 1)[-1] if site.startswith("http") else f"game{number}"


def warm_up() -> None:
    """Start Stockfish once before measuring: the first start of a session is slower
    because the engine's neural network still has to be read from disk."""
    with StockfishEngine(settings.STOCKFISH_PATH, depth=10) as engine:
        engine.evaluate(chess.Board())


def _timed_run(game, depth: int, check_great: bool = True, stats: dict | None = None):
    with stopwatch() as watch:
        _, mistake_rows = evaluate_moves(game, depth, check_great=check_great, stats=stats)
    return watch["seconds"], mistake_rows


def evaluate_game(
    game: chess.pgn.Game, number: int, depth: int, great_overhead: bool = False, repeats: int = 1
) -> dict:
    """One CSV row: run our analysis on the game at `depth` and compare with Lichess.

    seconds is the median of `repeats` timed runs; memory comes from one extra run.
    """
    stats = {}
    times = []
    for _ in range(max(1, repeats)):
        seconds, mistake_rows = _timed_run(game, depth, stats=stats)
        times.append(seconds)
    seconds = round(statistics.median(times), 3)
    with python_memory() as memory:
        evaluate_moves(game, depth)
    plies = len(list(game.mainline_moves()))

    seconds_without_great = overhead = None
    if great_overhead:
        if stats["great_checks"]:
            plain = [_timed_run(game, depth, check_great=False)[0] for _ in range(max(1, repeats))]
            seconds_without_great = round(statistics.median(plain), 3)
            overhead = round(100 * (seconds - seconds_without_great) / seconds_without_great, 1)
        else:
            seconds_without_great, overhead = seconds, 0.0  # no extra searches were made

    ours = {row["ply"]: row["severity"] for row in mistake_rows}
    result = compare(ours, lichess_labels(game), plies)
    return {
        "game": _name(game, number),
        "white": game.headers.get("White", "?"),
        "black": game.headers.get("Black", "?"),
        "result": game.headers.get("Result", "*"),
        "plies": plies,
        "depth": depth,
        "seconds": seconds,
        "repeats": len(times),
        "ms_per_move": round(1000 * seconds / plies),
        "python_peak_mb": memory["peak_mb"],
        "engine_peak_mb": stats.get("engine_peak_mb"),
        "great_checks": stats.get("great_checks"),
        "seconds_without_great": seconds_without_great,
        "great_overhead_pct": overhead,
        **{key: value for key, value in result.items() if key != "confusion"},
        "confusion": result["confusion"],
    }


def write_csv(rows: list[dict], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def summarize(rows: list[dict]) -> list[dict]:
    """One summary per depth: totals over all games (micro-averaged precision/recall/F1)."""
    summary = []
    for depth in sorted({row["depth"] for row in rows}):
        group = [row for row in rows if row["depth"] == depth]
        true_pos = sum(row["true_pos"] for row in group)
        kinds = ("none", *SEVERITIES)
        confusion = {lichess: {our: 0 for our in kinds} for lichess in kinds}
        for row in group:
            for lichess in kinds:
                for our in kinds:
                    confusion[lichess][our] += row["confusion"][lichess][our]
        summary.append({
            "depth": depth,
            "games": len(group),
            "plies": sum(row["plies"] for row in group),
            "total_seconds": round(sum(row["seconds"] for row in group), 1),
            "mean_seconds_per_game": _mean(row["seconds"] for row in group),
            "mean_ms_per_move": _mean(row["ms_per_move"] for row in group),
            "max_python_peak_mb": max((row["python_peak_mb"] for row in group), default=None),
            "max_engine_peak_mb": max((row["engine_peak_mb"] or 0 for row in group), default=None) or None,
            "mean_great_overhead_pct": _mean(row["great_overhead_pct"] for row in group),
            "lichess_labels": sum(row["lichess_labels"] for row in group),
            "our_labels": sum(row["our_labels"] for row in group),
            "true_pos": true_pos,
            "same_severity": sum(row["same_severity"] for row in group),
            **scores(
                true_pos,
                sum(row["false_pos"] for row in group),
                sum(row["false_neg"] for row in group),
            ),
            "confusion": confusion,
        })
    return summary


def format_summary(summary: list[dict]) -> str:
    """Plain-text tables for the terminal and the report."""
    lines = []
    for s in summary:
        same = f"{s['same_severity']}/{s['true_pos']}" if s["true_pos"] else "-"
        lines += [
            f"Depth {s['depth']}: {s['games']} games, {s['plies']} moves",
            f"  Latency : {s['total_seconds']} s in total, {s['mean_seconds_per_game']} s per game, "
            f"{s['mean_ms_per_move']} ms per move",
            f"  Memory  : Python peak {s['max_python_peak_mb']} MB, Stockfish peak {s['max_engine_peak_mb']} MB",
        ]
        if s["mean_great_overhead_pct"] is not None:
            lines.append(f"  Great check costs {s['mean_great_overhead_pct']}% extra time on average")
        lines += [
            f"  Accuracy: precision {s['precision']}, recall {s['recall']}, F1 {s['f1']} "
            f"(Lichess {s['lichess_labels']} labels, ours {s['our_labels']}, both {s['true_pos']}, "
            f"same severity {same})",
            "  Confusion (rows = Lichess, columns = ours):",
            "    " + "".join(f"{kind:>12}" for kind in ("", "none", *SEVERITIES)),
        ]
        for lichess, counts in s["confusion"].items():
            lines.append("    " + f"{lichess:>12}" + "".join(f"{counts[our]:>12}" for our in counts))
        lines.append("")
    return "\n".join(lines)
