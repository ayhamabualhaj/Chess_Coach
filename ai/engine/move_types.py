"""Chess.com-style move types: Brilliant, Great, Best, Excellent, Good, Miss,
Inaccuracy, Mistake, Blunder.

Pure Python, no Django. Based on Chess.com's help article "How are moves
classified?" (support.chess.com/en/articles/8572705): a move is judged by how
many "expected points" it loses (1 = winning, 0.5 = equal, 0 = losing).
Chess.com's exact model (which also uses the players' ratings) is not public,
so this is an approximation:
- Best: Stockfish's top move. Excellent: loses up to 0.02 points. Good: up to 0.05.
- Inaccuracy / Mistake / Blunder: the Lichess rules in move_classifier.py
  (they start exactly where Good ends: 0.05 points = 0.1 winning chances).
- Great: the best move, not an obvious one (out of check, a recapture, a free piece),
  and every other move would have been at least a mistake.
- Brilliant: a good piece sacrifice, when the player was not already winning easily.
- Miss: the opponent just made a mistake or blunder and the player did not punish it.
"""
import chess

from .move_classifier import BLUNDER, MISTAKE, Score, winning_chances

BRILLIANT = "brilliant"
GREAT = "great"
BEST = "best"
EXCELLENT = "excellent"
GOOD = "good"
MISS = "miss"

EXCELLENT_MAX_LOSS = 0.02  # expected points
GOOD_MAX_LOSS = 0.05
# Great: the second-best move would have lost at least this many expected points
# (0.1 points = 0.2 winning chances = a Lichess "Mistake").
GREAT_MIN_GAP = 0.10
# Positions that are already decided have no Great or Brilliant moves.
DECIDED = 0.90  # expected points
GREAT_MIN_PLY = 11  # the first 5 moves of each side are opening theory
# Brilliant: after the sacrifice the player must not be clearly worse.
NOT_WORSE = 0.40  # expected points

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def expected_points(score: Score, mover_is_white: bool) -> float:
    """0 (losing) to 1 (winning) for the side to judge, like Chess.com's expected points."""
    return (winning_chances(score.for_side(mover_is_white).capped_cp()) + 1) / 2


def points_lost(before: Score, after: Score, mover_is_white: bool) -> float:
    return max(0.0, expected_points(before, mover_is_white) - expected_points(after, mover_is_white))


def is_sacrifice(board: chess.Board, move: chess.Move) -> bool:
    """The move puts a piece (knight or bigger) where the opponent can win it,
    and gives away more than it takes. `board` is the position before the move."""
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type in (chess.PAWN, chess.KING) or move.promotion:
        return False
    captured = board.piece_at(move.to_square)
    captured_value = PIECE_VALUES[captured.piece_type] if captured else 0
    if PIECE_VALUES[piece.piece_type] - captured_value < 2:
        return False

    after = board.copy(stack=False)
    after.push(move)
    attackers = after.attackers(not piece.color, move.to_square)
    if not attackers:
        return False
    cheapest = min(PIECE_VALUES[after.piece_at(square).piece_type] for square in attackers)
    defended = bool(after.attackers(piece.color, move.to_square))
    return not defended or cheapest < PIECE_VALUES[piece.piece_type]


def _is_obvious(board: chess.Board, move: chess.Move) -> bool:
    """Moves anyone would find: getting out of check, taking back a piece that was
    just captured, or taking a piece that is undefended or worth more than the taker."""
    if board.is_check():
        return True
    if not board.is_capture(move):
        return False
    last = board.peek() if board.move_stack else None
    if last is not None and last.to_square == move.to_square:
        return True  # recapture
    if board.is_en_passant(move):
        return False
    taker, victim = board.piece_at(move.from_square), board.piece_at(move.to_square)
    undefended = not board.attackers(victim.color, move.to_square)
    return undefended or PIECE_VALUES[victim.piece_type] > PIECE_VALUES[taker.piece_type]


def should_check_great(board: chess.Board, move: chess.Move, before: Score, played_best: bool, ply: int) -> bool:
    """Whether to run the slow "is every other move clearly worse?" search.

    Only the engine's best move can be Great, so the search is skipped for every
    other move, for obvious and forced moves, in the first opening moves and when
    the game is already decided. `board` is the position before the move.
    """
    if not played_best or ply < GREAT_MIN_PLY or board.legal_moves.count() < 2:
        return False
    if _is_obvious(board, move):
        return False
    points = expected_points(before, board.turn == chess.WHITE)
    return 1 - DECIDED < points < DECIDED


def move_type(
    before: Score,
    after: Score,
    mover_is_white: bool,
    played_best: bool,
    severity: str | None = None,
    opponent_severity: str | None = None,
    sacrifice: bool = False,
    second_best: Score | None = None,
) -> str:
    """The move's type. severity is the Lichess label of this move (or None);
    opponent_severity the label of the opponent's previous move; second_best the
    evaluation of the best move other than Stockfish's choice (only when checked)."""
    if severity:
        if opponent_severity in (MISTAKE, BLUNDER):
            return MISS
        return severity

    lost = points_lost(before, after, mover_is_white)
    before_points = expected_points(before, mover_is_white)
    after_points = expected_points(after, mover_is_white)

    if sacrifice and lost <= EXCELLENT_MAX_LOSS and after_points >= NOT_WORSE and before_points < DECIDED:
        return BRILLIANT
    if played_best and second_best is not None:
        if before_points - expected_points(second_best, mover_is_white) >= GREAT_MIN_GAP:
            return GREAT
    if played_best:
        return BEST
    if lost <= EXCELLENT_MAX_LOSS:
        return EXCELLENT
    # Up to GOOD_MAX_LOSS; anything worse already has a Lichess severity.
    return GOOD
