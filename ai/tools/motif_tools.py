"""Simple tactical pattern detection for a single move, using python-chess.

Pure Python, no Django. These are deliberately simple rules (not a full
tactics engine): they describe *why* a move was bad in words a player
understands, e.g. "you left a piece hanging" or "you missed a fork".
"""
import chess

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

ALLOWED_MATE = "allowed_mate"
MISSED_MATE = "missed_mate"
HANGING_PIECE = "hanging_piece"
MISSED_FORK = "missed_fork"
MISSED_CAPTURE = "missed_capture"
MISSED_CHECK = "missed_check"
# Longer mates found by the engine rather than by the board rules above.
ALLOWED_FORCED_MATE = "allowed_forced_mate"
MISSED_FORCED_MATE = "missed_forced_mate"

# When several patterns apply, the first one in this list is the main explanation.
MOTIF_PRIORITY = [ALLOWED_MATE, MISSED_MATE, HANGING_PIECE, MISSED_FORK, MISSED_CAPTURE, MISSED_CHECK]


def _captured_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return PIECE_VALUES[chess.PAWN]
    piece = board.piece_at(move.to_square)
    return PIECE_VALUES[piece.piece_type] if piece else 0


def _allows_mate_in_one(board_after: chess.Board) -> bool:
    for reply in board_after.legal_moves:
        board_after.push(reply)
        is_mate = board_after.is_checkmate()
        board_after.pop()
        if is_mate:
            return True
    return False


def _hanging_pieces(board_after: chess.Board, color: chess.Color) -> list[chess.Square]:
    """Pieces of `color` (not pawns or king) that the opponent can win right now:
    attacked and either undefended or attacked by a cheaper piece."""
    hanging = []
    for square, piece in board_after.piece_map().items():
        if piece.color != color or piece.piece_type in (chess.PAWN, chess.KING):
            continue
        attackers = board_after.attackers(not color, square)
        if not attackers:
            continue
        cheapest_attacker = min(PIECE_VALUES[board_after.piece_at(s).piece_type] for s in attackers)
        defended = bool(board_after.attackers(color, square))
        if not defended or cheapest_attacker < PIECE_VALUES[piece.piece_type]:
            hanging.append(square)
    return hanging


def _is_fork(board_after: chess.Board, square: chess.Square) -> bool:
    """The piece on `square` attacks two or more valuable enemy pieces (or the king and one)."""
    piece = board_after.piece_at(square)
    targets = 0
    for target in board_after.attacks(square):
        victim = board_after.piece_at(target)
        if victim and victim.color != piece.color:
            if victim.piece_type == chess.KING or PIECE_VALUES[victim.piece_type] >= 3:
                targets += 1
    return targets >= 2


def detect_motifs(fen_before: str, played_uci: str, best_uci: str = "") -> list[str]:
    """All patterns that explain why `played_uci` was worse than `best_uci`,
    most important first."""
    board = chess.Board(fen_before)
    mover = board.turn
    played = chess.Move.from_uci(played_uci)
    best = chess.Move.from_uci(best_uci) if best_uci and best_uci != played_uci else None
    found = set()

    after_played = board.copy()
    after_played.push(played)

    if _allows_mate_in_one(after_played):
        found.add(ALLOWED_MATE)

    # A piece left en prise, unless the move itself won at least as much (a fair trade).
    won_now = _captured_value(board, played)
    for square in _hanging_pieces(after_played, mover):
        if PIECE_VALUES[after_played.piece_at(square).piece_type] > won_now:
            found.add(HANGING_PIECE)
            break

    if best is not None:
        after_best = board.copy()
        after_best.push(best)
        if after_best.is_checkmate():
            found.add(MISSED_MATE)
        else:
            if _is_fork(after_best, best.to_square) and not _is_fork(after_played, played.to_square):
                found.add(MISSED_FORK)
            if board.gives_check(best) and not board.gives_check(played):
                found.add(MISSED_CHECK)
        if _captured_value(board, best) >= 3 and _captured_value(board, played) < _captured_value(board, best):
            found.add(MISSED_CAPTURE)

    return [motif for motif in MOTIF_PRIORITY if motif in found]


def primary_motif(fen_before: str, played_uci: str, best_uci: str = "") -> str:
    """The single most important pattern, or "" if none of the simple rules apply."""
    motifs = detect_motifs(fen_before, played_uci, best_uci)
    return motifs[0] if motifs else ""


def engine_mate_motif(mate_before: int | None, mate_after: int | None, mover_is_white: bool) -> str:
    """Use the engine's mate scores (from White's point of view) to spot longer mates."""
    sign = 1 if mover_is_white else -1
    before = None if mate_before is None else mate_before * sign
    after = None if mate_after is None else mate_after * sign
    if after is not None and after < 0 and (before is None or before > 0):
        return ALLOWED_FORCED_MATE
    if before is not None and before > 0 and (after is None or after < 0):
        return MISSED_FORCED_MATE
    return ""