import io
from contextlib import ExitStack

import chess
import chess.pgn
from django.conf import settings

from ai.engine import (
    EngineNotFoundError, Score, StockfishEngine, centipawn_loss, classify_move, game_phase,
    is_sacrifice, move_type, should_check_great,
)
from ai.engine.move_types import BEST
from ai.engine.stockfish_wrapper import MATE_SCORE
from ai.tools import engine_mate_motif, primary_motif
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
        message = "The stored PGN could not be read."
        game_repository.set_status(game, Game.Status.FAILED, message)
        raise AnalysisError(message)

    game_repository.set_status(game, Game.Status.RUNNING)
    try:
        move_rows, mistake_rows = _evaluate_moves(parsed, depth or settings.STOCKFISH_DEPTH)
        analysis_repository.replace_analysis(game, move_rows, mistake_rows)
    except EngineNotFoundError as e:
        message = "The chess engine is not available. Check STOCKFISH_PATH."
        game_repository.set_status(game, Game.Status.FAILED, message)
        raise AnalysisError(message) from e
    except Exception:
        game_repository.set_status(game, Game.Status.FAILED, "Unexpected error during analysis.")
        raise

    game_repository.set_status(game, Game.Status.DONE)
    return {"moves": len(move_rows), "mistakes": len(mistake_rows)}


def _evaluate_moves(parsed_game, depth: int) -> tuple[list[dict], list[dict]]:
    move_rows, mistake_rows = [], []
    board = parsed_game.board()
    previous_label = None  # Lichess label of the opponent's last move, for "Miss"

    with ExitStack() as engines:
        engine = engines.enter_context(StockfishEngine(settings.STOCKFISH_PATH, depth=depth))
        # A second engine, started only when needed, for the "was it the only good
        # move?" search. Using the main engine for it would change what that engine
        # remembers (its hash table) and so, slightly, the evaluations of later moves.
        checker = None

        # Each position is evaluated once: the "after" of one move is the
        # "before" of the next.
        before = engine.evaluate(board)

        for ply, move in enumerate(parsed_game.mainline_moves(), start=1):
            mover_is_white = board.turn == chess.WHITE
            fen_before = board.fen()
            san = board.san(move)
            phase = game_phase(board, ply)
            played_best = before.best_move == move
            sacrifice = is_sacrifice(board, move)

            # Great needs a second search: is every other move clearly worse?
            # Only done when the player found the best move, so it costs little.
            second_best = None
            if should_check_great(board, move, _to_score(before), played_best, ply):
                if checker is None:
                    checker = engines.enter_context(StockfishEngine(settings.STOCKFISH_PATH, depth=depth))
                alternative = checker.evaluate_without(board, move)
                second_best = _to_score(alternative) if alternative else None

            board.push(move)
            if board.is_checkmate():
                # The mover just won; nothing to evaluate and nothing to criticise.
                after = None
                eval_after = MATE_SCORE if mover_is_white else -MATE_SCORE
                cp_loss, label, kind = 0, None, BEST
            else:
                after = engine.evaluate(board)
                eval_after = after.cp
                cp_loss = centipawn_loss(_to_score(before), _to_score(after), mover_is_white)
                label = classify_move(_to_score(before), _to_score(after), mover_is_white)
                kind = move_type(
                    _to_score(before), _to_score(after), mover_is_white, played_best,
                    severity=label, opponent_severity=previous_label,
                    sacrifice=sacrifice, second_best=second_best,
                )

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
                "label": kind,
            })
            if label:
                best_uci = before.best_move.uci() if before.best_move else ""
                mistake_rows.append({
                    "ply": ply,
                    "severity": label,
                    "phase": phase,
                    "motif": (
                            primary_motif(fen_before, move.uci(), best_uci)
                            or engine_mate_motif(before.mate, after.mate, mover_is_white)
                    ),
                })

            if after is None:
                break
            before = after
            previous_label = label

    return move_rows, mistake_rows
