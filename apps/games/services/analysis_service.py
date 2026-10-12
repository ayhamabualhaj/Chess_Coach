import io

import chess
import chess.pgn
from django.conf import settings

from ai.engine import Score, StockfishEngine, centipawn_loss, classify_move, game_phase
from ai.engine.stockfish_wrapper import MATE_SCORE
from apps.games.models import Game
from apps.games.repositories import analysis_repository, game_repository


class AnalysisError(Exception):
    pass


def _to_score(position_eval) -> Score:
    if position_eval.mate is not None:
        return Score(mate=position_eval.mate)
    return Score(cp=position_eval.cp)


def analyse_game(game_id: int, depth: int | None = None) -> dict:
    """Run Stockfish over every move of a game and store evaluations and mistakes.

    Returns a small summary, e.g. {"moves": 40, "mistakes": 5}.
    """
    game = game_repository.get_game(game_id)
    parsed = chess.pgn.read_game(io.StringIO(game.pgn))
    if parsed is None:
        game_repository.set_status(game, Game.Status.FAILED)
        raise AnalysisError("The stored PGN could not be read.")

    game_repository.set_status(game, Game.Status.RUNNING)
    try:
        move_rows, mistake_rows = _evaluate_moves(parsed, depth or settings.STOCKFISH_DEPTH)
        analysis_repository.replace_analysis(game, move_rows, mistake_rows)
    except Exception:
        game_repository.set_status(game, Game.Status.FAILED)
        raise

    game_repository.set_status(game, Game.Status.DONE)
    return {"moves": len(move_rows), "mistakes": len(mistake_rows)}


def _evaluate_moves(parsed_game, depth: int) -> tuple[list[dict], list[dict]]:
    move_rows, mistake_rows = [], []
    board = parsed_game.board()

    with StockfishEngine(settings.STOCKFISH_PATH, depth=depth) as engine:
        # Each position is evaluated once: the "after" of one move is the
        # "before" of the next.
        before = engine.evaluate(board)

        for ply, move in enumerate(parsed_game.mainline_moves(), start=1):
            mover_is_white = board.turn == chess.WHITE
            fen_before = board.fen()
            san = board.san(move)
            phase = game_phase(board, ply)

            board.push(move)
            if board.is_checkmate():
                # The mover just won; nothing to evaluate and nothing to criticise.
                after = None
                eval_after = MATE_SCORE if mover_is_white else -MATE_SCORE
                cp_loss, label = 0, None
            else:
                after = engine.evaluate(board)
                eval_after = after.cp
                cp_loss = centipawn_loss(_to_score(before), _to_score(after), mover_is_white)
                label = classify_move(_to_score(before), _to_score(after), mover_is_white)

            move_rows.append({
                "ply": ply,
                "color": "white" if mover_is_white else "black",
                "san": san,
                "uci": move.uci(),
                "fen_before": fen_before,
                "eval_before": before.cp,
                "eval_after": eval_after,
                "best_move_uci": before.best_move.uci() if before.best_move else "",
                "cp_loss": cp_loss,
            })
            if label:
                mistake_rows.append({"ply": ply, "severity": label, "phase": phase})

            if after is None:
                break
            before = after

    return move_rows, mistake_rows