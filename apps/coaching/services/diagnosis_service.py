"""Runs the diagnosis agent for one WeaknessReport (called from the background task)."""
import io

import chess
import chess.pgn
from django.conf import settings

from ai.agents.diagnosis_agent import DiagnosisAgent, DiagnosisError
from ai.engine import game_phase
from ai.tools import MoveRecord, opening_label
from apps.accounts.repositories import account_repository
from apps.coaching.models import WeaknessReport
from apps.coaching.repositories import report_repository
from apps.games.models import Mistake
from apps.games.repositories import game_repository


def _make_agent() -> DiagnosisAgent:
    # Tests replace this function with one that returns a fake agent.
    return DiagnosisAgent(model=settings.ANTHROPIC_MODEL)


def _opening_of(game) -> str:
    parsed = chess.pgn.read_game(io.StringIO(game.pgn))
    if parsed is None:
        return ""
    board = parsed.board()
    sans = []
    for move in list(parsed.mainline_moves())[:6]:
        sans.append(board.san(move))
        board.push(move)
    return opening_label(dict(parsed.headers), sans)


def build_move_records(user, games=None) -> list[MoveRecord]:
    """Turn the user's analysed moves (their own side only) into MoveRecords for the agent.

    games: the games to use; by default every game that is ready for coaching.
    """
    if games is None:
        games = game_repository.list_games_for_coaching(user)
    games = list(games)
    openings = {game.pk: _opening_of(game) for game in games}

    records = []
    for move in game_repository.list_user_moves(games):
        try:
            mistake = move.mistake
        except Mistake.DoesNotExist:
            mistake = None
        records.append(MoveRecord(
            game_id=move.game_id,
            ply=move.ply,
            san=move.san,
            fen_before=move.fen_before,
            phase=mistake.phase if mistake else game_phase(chess.Board(move.fen_before), move.ply),
            cp_loss=move.cp_loss or 0,
            severity=mistake.severity if mistake else "",
            motif=mistake.motif if mistake else "",
            opening=openings[move.game_id],
            best_move_uci=move.best_move_uci,
        ))
    return records


def run_report(report_id: int) -> None:
    report = report_repository.get_report(report_id)
    report_repository.set_status(report, WeaknessReport.Status.RUNNING)

    if not settings.ANTHROPIC_API_KEY:
        report_repository.set_status(
            report, WeaknessReport.Status.FAILED, "No ANTHROPIC_API_KEY found in .env."
        )
        return

    records = build_move_records(report.user, report_repository.list_report_games(report))
    if not records:
        report_repository.set_status(
            report, WeaknessReport.Status.FAILED, "None of the chosen games has analysed moves."
        )
        return
    profile = account_repository.get_profile(report.user)
    player = {"name": report.user.username, "rating": profile.rating if profile else None}

    try:
        result = _make_agent().run(records, player=player)
    except DiagnosisError as e:
        report_repository.set_status(report, WeaknessReport.Status.FAILED, str(e))
        return
    except Exception:
        report_repository.set_status(
            report, WeaknessReport.Status.FAILED, "Unexpected error while preparing the report."
        )
        raise

    report_repository.save_result(
        report,
        games_count=len({r.game_id for r in records}),
        moves_count=len(records),
        summary=result.summary,
        weaknesses=result.weaknesses,
        ai_model=result.model,
        turns=result.turns,
        tool_calls=[
            {"name": c.name, "seconds": round(c.seconds, 3), "is_error": c.is_error}
            for c in result.tool_calls
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        seconds=round(result.seconds, 2),
    )
    plan = result.training_plan
    if plan:
        report_repository.save_training_plan(report, plan["overview"], plan["days"], plan["tasks"])