import chess
from django.conf import settings
from django.core.paginator import Paginator

from ai.engine import game_accuracy
from apps.games.models import Game, Mistake, Move
from apps.games.repositories import game_repository
from apps.games.tasks import analyse_game_task

# The graph is cut off at +/- 10 pawns so one mate score doesn't flatten everything else.
CHART_LIMIT_PAWNS = 10
GAMES_PER_PAGE = 50

# What request_analysis can answer.
QUEUED = "queued"
ALREADY_QUEUED = "already_queued"
QUEUE_FULL = "queue_full"

# How each move type looks on the game page: symbol and colour class.
LABEL_STYLES = {
    Move.Label.BRILLIANT: "!!",
    Move.Label.GREAT: "!",
    Move.Label.BEST: "★",
    Move.Label.EXCELLENT: "👍",
    Move.Label.GOOD: "✓",
    Move.Label.MISS: "✗",
    Move.Label.INACCURACY: "?!",
    Move.Label.MISTAKE: "?",
    Move.Label.BLUNDER: "??",
}


def list_games(user, show: str = "all", page: int | str = 1) -> dict:
    """One page of the user's games, optionally filtered (all / todo / done / side)."""
    if show not in game_repository.GAME_FILTERS:
        show = "all"
    paginator = Paginator(game_repository.list_games_for_user(user, show), GAMES_PER_PAGE)
    return {
        "page": paginator.get_page(page),
        "show": show,
        "counts": game_repository.count_games_by_filter(user),
        "in_progress": game_repository.count_in_progress(user),
        "to_analyse": game_repository.count_games_to_analyse(user),
        "max_queue": settings.MAX_ANALYSIS_QUEUE,
    }

def filter_games(user, show: str = "all"):
    """The user's games for one filter (all / todo / done / side), newest first."""
    if show not in game_repository.GAME_FILTERS:
        show = "all"
    return game_repository.list_games_for_user(user, show)

def get_game(user, game_id: int):
    return game_repository.get_game_for_user(user, game_id)


def delete_game(game: Game) -> None:
    game_repository.delete_game(game)


def delete_games(user, game_ids) -> int:
    """Delete several of the user's games at once; ids of other users' games are ignored."""
    ids = [int(i) for i in game_ids if str(i).isdigit()]
    return game_repository.delete_games(user, ids) if ids else 0


def set_user_color(game: Game, color: str) -> bool:
    """Record which side the user played. Returns False for an invalid colour."""
    if color not in Game.Side.values:
        return False
    game_repository.set_user_color(game, color)
    return True


def count_in_progress(user) -> int:
    return game_repository.count_in_progress(user)


def queue_space(user) -> int:
    """How many more games the user may put in the analysis queue right now."""
    return max(0, settings.MAX_ANALYSIS_QUEUE - game_repository.count_in_progress(user))


def _enqueue(game: Game) -> None:
    game_repository.set_status(game, Game.Status.QUEUED)
    analyse_game_task.enqueue(game.pk)


def request_analysis(game: Game) -> str:
    """Put the game in the background queue.

    Returns QUEUED, ALREADY_QUEUED, or QUEUE_FULL when the user already has
    MAX_ANALYSIS_QUEUE games waiting (so one user cannot keep the worker busy for hours).
    """
    if game.status in game_repository.IN_PROGRESS:
        return ALREADY_QUEUED
    if queue_space(game.user) == 0:
        return QUEUE_FULL
    _enqueue(game)
    return QUEUED


def analyse_all(user) -> dict:
    """Queue as many not-yet-analysed games as the queue has room for.

    Returns {"queued": n, "waiting": games still not queued}.
    """
    games = game_repository.list_games_to_analyse(user, queue_space(user))
    for game in games:
        _enqueue(game)
    return {"queued": len(games), "waiting": game_repository.count_games_to_analyse(user)}


def get_game_detail(user, game_id: int) -> dict | None:
    """Everything the game page needs, or None if the user has no such game."""
    game = game_repository.get_game_for_user(user, game_id)
    if game is None:
        return None

    moves = list(game_repository.list_moves_with_mistakes(game))
    accuracy = _accuracy(moves)
    return {
        "game": game,
        "in_progress": game.status in game_repository.IN_PROGRESS,
        "rows": _move_rows(moves),
        "stats": {
            "white": _side_stats(moves, "white", accuracy["white"]),
            "black": _side_stats(moves, "black", accuracy["black"]),
        },
        "chart": _chart_data(moves),
        "has_labels": any(move.label for move in moves),
    }


def get_game_analysis(user, game_id: int) -> dict | None:
    """A game with its moves (and their mistakes) and the accuracy of both sides."""
    game = game_repository.get_game_for_user(user, game_id)
    if game is None:
        return None
    moves = list(game_repository.list_moves_with_mistakes(game))
    return {"game": game, "moves": moves, "accuracy": _accuracy(moves)}



def _mistake_of(move):
    try:
        return move.mistake
    except Mistake.DoesNotExist:
        return None


def _best_move_san(move) -> str:
    if not move.best_move_uci or move.best_move_uci == move.uci:
        return ""
    board = chess.Board(move.fen_before)
    return board.san(chess.Move.from_uci(move.best_move_uci))


def _move_rows(moves) -> list[dict]:
    """Pair moves into table rows: 1. e4 e5 / 2. Nf3 Nc6 / ..."""
    rows = {}
    for move in moves:
        number = (move.ply + 1) // 2
        mistake = _mistake_of(move)
        cell = {
            "san": move.san,
            "cp_loss": move.cp_loss,
            "mistake": mistake,
            "label": move.label,
            "label_name": move.get_label_display() if move.label else "",
            "symbol": LABEL_STYLES.get(move.label, ""),
            "best_san": _best_move_san(move) if mistake else "",
        }
        rows.setdefault(number, {"number": number, "white": None, "black": None})
        rows[number][move.color] = cell
    return list(rows.values())


def _accuracy(moves) -> dict:
    """Lichess-style accuracy % per side (None before the game is analysed)."""
    complete = moves and moves[0].ply == 1 and moves[0].color == "white"
    if not complete or any(m.eval_before is None or m.eval_after is None for m in moves):
        return {"white": None, "black": None}
    return game_accuracy(moves[0].eval_before, [m.eval_after for m in moves])


def _side_stats(moves, color: str, accuracy: float | None) -> dict:
    side = [m for m in moves if m.color == color]
    losses = [m.cp_loss for m in side if m.cp_loss is not None]
    counts = {severity: 0 for severity in Mistake.Severity.values}
    for move in side:
        mistake = _mistake_of(move)
        if mistake:
            counts[mistake.severity] += 1
    labels = [
        {"label": label, "name": name, "symbol": LABEL_STYLES[label],
         "count": sum(1 for m in side if m.label == label)}
        for label, name in Move.Label.choices
    ]
    return {
        "moves": len(side),
        "avg_cp_loss": round(sum(losses) / len(losses)) if losses else None,
        "accuracy": accuracy,
        "labels": labels,
        **counts,
    }


def _to_pawns(cp: int) -> float:
    return max(-CHART_LIMIT_PAWNS, min(CHART_LIMIT_PAWNS, cp / 100))


def _chart_data(moves) -> dict:
    if not moves:
        return {"labels": [], "evals": []}
    labels = ["Start"]
    evals = [_to_pawns(moves[0].eval_before)]
    for move in moves:
        number = (move.ply + 1) // 2
        labels.append(f"{number}. {move.san}" if move.color == "white" else f"{number}... {move.san}")
        evals.append(_to_pawns(move.eval_after))
    return {"labels": labels, "evals": evals}
