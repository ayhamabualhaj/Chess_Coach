"""Rules that turn engine evaluations into mistake labels.

Pure Python, no Django. The labelling follows Lichess's open-source rules
(lichess-org/lila, modules/tree/src/main/Advice.scala, and the win-chance
formula in lichess-org/scalachess, core/src/main/scala/eval.scala), so our
labels can be compared with the ones Lichess writes into its PGN exports.
"""
import math
from dataclasses import dataclass

import chess

INACCURACY = "inaccuracy"
MISTAKE = "mistake"
BLUNDER = "blunder"

OPENING = "opening"
MIDDLEGAME = "middlegame"
ENDGAME = "endgame"

# Lichess caps evaluations at +/- 10 pawns when turning them into percentages.
CP_CEILING = 1000
# Lichess's fitted constant for converting centipawns to winning chances.
WIN_CHANCE_MULTIPLIER = -0.00368208
# A drop in winning chances (scale -1..1) of at least this much gets the label.
WIN_CHANCE_THRESHOLDS = [(0.3, BLUNDER), (0.2, MISTAKE), (0.1, INACCURACY)]
OPENING_PLIES = 20  # the first 10 moves of each side


@dataclass(frozen=True)
class Score:
    """An evaluation from White's point of view: either centipawns or mate-in-N."""

    cp: int | None = None
    mate: int | None = None  # + White mates, - Black mates

    def for_side(self, white: bool) -> "Score":
        if white:
            return self
        return Score(
            cp=None if self.cp is None else -self.cp,
            mate=None if self.mate is None else -self.mate,
        )

    def capped_cp(self) -> int:
        if self.mate is not None:
            return CP_CEILING if self.mate > 0 else -CP_CEILING
        return max(-CP_CEILING, min(CP_CEILING, self.cp))


def winning_chances(cp: int) -> float:
    """Centipawns -> winning chances between -1 (lost) and +1 (won)."""
    return 2 / (1 + math.exp(WIN_CHANCE_MULTIPLIER * cp)) - 1


def classify_move(before: Score, after: Score, mover_is_white: bool) -> str | None:
    """Label a move from the evaluations before and after it, or None if it was fine."""
    prev = before.for_side(mover_is_white)
    cur = after.for_side(mover_is_white)

    # Normal case: both sides of the move are centipawn scores.
    if prev.cp is not None and cur.cp is not None:
        drop = winning_chances(prev.cp) - winning_chances(cur.cp)
        for threshold, label in WIN_CHANCE_THRESHOLDS:
            if drop >= threshold:
                return label
        return None

    # The move allowed a forced mate against the mover.
    if prev.cp is not None and cur.mate is not None and cur.mate < 0:
        if prev.cp < -999:
            return INACCURACY  # already completely lost
        if prev.cp < -700:
            return MISTAKE
        return BLUNDER

    # The mover had a forced mate and let it slip.
    if prev.mate is not None and prev.mate > 0:
        if cur.cp is not None or (cur.mate is not None and cur.mate < 0):
            cur_cp = cur.cp or 0
            if cur_cp > 999:
                return INACCURACY  # still completely winning
            if cur_cp > 700:
                return MISTAKE
            return BLUNDER

    return None


def centipawn_loss(before: Score, after: Score, mover_is_white: bool) -> int:
    """How many centipawns the move gave away, for the side that played it."""
    prev = before.for_side(mover_is_white).capped_cp()
    cur = after.for_side(mover_is_white).capped_cp()
    return max(0, prev - cur)


def _has_endgame_material(board: chess.Board, color: chess.Color) -> bool:
    queens = len(board.pieces(chess.QUEEN, color))
    if queens == 0:
        return True
    rooks = len(board.pieces(chess.ROOK, color))
    minors = len(board.pieces(chess.KNIGHT, color)) + len(board.pieces(chess.BISHOP, color))
    return queens == 1 and rooks == 0 and minors <= 1


def game_phase(board: chess.Board, ply: int) -> str:
    """Opening for the first 10 moves; endgame once neither side has much
    left besides pawns (no queen, or a queen with at most one minor piece)."""
    if ply <= OPENING_PLIES:
        return OPENING
    if _has_endgame_material(board, chess.WHITE) and _has_endgame_material(board, chess.BLACK):
        return ENDGAME
    return MIDDLEGAME