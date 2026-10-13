"""Accuracy % per side, computed the same way Lichess does.

Pure Python, no Django. Copied from Lichess's open-source code:
- lichess-org/lila, modules/analyse/src/main/AccuracyPercent.scala
  (accuracy of one move, and the game accuracy = mean of a volatility-weighted
  mean and a harmonic mean)
- lichess-org/scalachess, core/src/main/scala/eval.scala (win percent)
- lichess-org/scalalib, lila/src/main/scala/Maths.scala (the means and the
  population standard deviation)
"""
import math

from .move_classifier import CP_CEILING, winning_chances


def win_percent(cp: int) -> float:
    """Centipawns from White's view -> White's chance of winning, 0 to 100."""
    return 50 + 50 * winning_chances(max(-CP_CEILING, min(CP_CEILING, cp)))


def move_accuracy(before: float, after: float) -> float:
    """Accuracy (0-100) of one move, from the mover's win percent before and after it."""
    if after >= before:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * (before - after)) - 3.166924740191411
    return max(0.0, min(100.0, raw + 1))  # +1: Lichess's bonus for imperfect analysis


def _std_dev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _harmonic_mean(values: list[float]) -> float:
    return len(values) / sum(1 / max(1, v) for v in values)


def game_accuracy(start_cp: int, cps_after: list[int]) -> dict:
    """Accuracy of White and Black for a game that starts with White to move.

    start_cp: evaluation of the starting position; cps_after: evaluation after
    each move, in order. All in centipawns from White's view.
    Returns {"white": 87.3, "black": 64.1} (None for a side without moves).
    """
    wins = [win_percent(cp) for cp in [start_cp, *cps_after]]
    window_size = max(2, min(8, len(cps_after) // 10))

    # Sliding windows over the win percents; the first ones are padded so there
    # is one window (and so one weight) per move.
    windows = [wins[:window_size]] * (min(window_size, len(wins)) - 2)
    windows += [wins[i:i + window_size] for i in range(max(1, len(wins) - window_size + 1))]
    weights = [max(0.5, min(12, _std_dev(window))) for window in windows]

    moves = {"white": [], "black": []}
    for i in range(len(wins) - 1):
        before, after = wins[i], wins[i + 1]
        if i % 2 == 0:
            moves["white"].append((move_accuracy(before, after), weights[i]))
        else:
            moves["black"].append((move_accuracy(100 - before, 100 - after), weights[i]))

    result = {}
    for side, scored in moves.items():
        if not scored:
            result[side] = None
            continue
        weighted = sum(a * w for a, w in scored) / sum(w for _, w in scored)
        harmonic = _harmonic_mean([a for a, _ in scored])
        result[side] = round((weighted + harmonic) / 2, 1)
    return result
