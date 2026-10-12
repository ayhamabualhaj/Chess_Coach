
import chess
from apps.games.models import Game, Mistake
from apps.games.tasks import analyse_game_task
from apps.games.models import Mistake
from apps.games.repositories import game_repository

# The graph is cut off at +/- 10 pawns so one mate score doesn't flatten everything else.
CHART_LIMIT_PAWNS = 10


def list_games(user):
    return game_repository.list_games_for_user(user)


def get_game(user, game_id: int):
    return game_repository.get_game_for_user(user, game_id)

def request_analysis(game: Game) -> bool:
    """Put the game in the background queue. Returns False if it is already queued or running."""
    if game.status in (Game.Status.QUEUED, Game.Status.RUNNING):
        return False
    game_repository.set_status(game, Game.Status.QUEUED)
    analyse_game_task.enqueue(game.pk)
    return True

def get_game_detail(user, game_id: int) -> dict | None:
    """Everything the game page needs, or None if the user has no such game."""
    game = game_repository.get_game_for_user(user, game_id)
    if game is None:
        return None

    moves = list(game_repository.list_moves_with_mistakes(game))
    return {
        "game": game,
        "in_progress": game.status in (Game.Status.QUEUED, Game.Status.RUNNING),
        "rows": _move_rows(moves),
        "stats": {"white": _side_stats(moves, "white"), "black": _side_stats(moves, "black")},
        "chart": _chart_data(moves),
    }


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
        cell = {
            "san": move.san,
            "cp_loss": move.cp_loss,
            "mistake": _mistake_of(move),
            "best_san": _best_move_san(move) if _mistake_of(move) else "",
        }
        rows.setdefault(number, {"number": number, "white": None, "black": None})
        rows[number][move.color] = cell
    return list(rows.values())


def _side_stats(moves, color: str) -> dict:
    side = [m for m in moves if m.color == color]
    losses = [m.cp_loss for m in side if m.cp_loss is not None]
    counts = {severity: 0 for severity in Mistake.Severity.values}
    for move in side:
        mistake = _mistake_of(move)
        if mistake:
            counts[mistake.severity] += 1
    return {
        "moves": len(side),
        "avg_cp_loss": round(sum(losses) / len(losses)) if losses else None,
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
