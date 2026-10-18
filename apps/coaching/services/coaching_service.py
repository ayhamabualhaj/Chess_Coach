from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.repositories import account_repository
from apps.coaching.models import WeaknessReport
from apps.coaching.repositories import report_repository
from apps.coaching.tasks import generate_report_task
from apps.games.repositories import game_repository


STUCK_MESSAGE = "The report stopped before it finished (the worker may have been restarted). Please create a new one."


class ReportRequestError(Exception):
    """A new report was refused (no games chosen, games not ready, one already running)."""


def recover_stuck_reports(user=None, minutes: int | None = None) -> int:
    """Mark reports waiting or running longer than STUCK_JOB_MINUTES as failed (all users if user is None)."""
    minutes = settings.STUCK_JOB_MINUTES if minutes is None else minutes
    older_than = timezone.now() - timedelta(minutes=minutes)
    return report_repository.fail_stuck_reports(older_than, STUCK_MESSAGE, user)


def get_overview(user) -> dict:
    """Everything the coaching page needs."""
    recover_stuck_reports(user)
    return {
        "games": game_repository.count_games_by_state(user),
        "ready_games": game_repository.list_games_for_coaching(user),
        "reports": report_repository.list_reports_for_user(user),
    }


def _parse_ids(game_ids) -> set[int]:
    try:
        return {int(game_id) for game_id in game_ids}
    except (TypeError, ValueError):
        raise ReportRequestError("Invalid game selection.")


def request_report(user, game_ids) -> WeaknessReport:
    """Queue a new report (weaknesses + training plan) for the chosen games."""
    chosen = _parse_ids(game_ids)
    if not chosen:
        raise ReportRequestError("Choose at least one game for the coach to study.")
    games = list(game_repository.get_ready_games(user, chosen))
    if len(games) != len(chosen):
        raise ReportRequestError(
            "Some chosen games are not ready: they must be analysed and have your side set."
        )
    with transaction.atomic():
        account_repository.lock_user(user)
        recover_stuck_reports(user)
        if report_repository.has_report_in_progress(user):
            raise ReportRequestError("A report is already being prepared.")
        report = report_repository.create_report(user, games)
        generate_report_task.enqueue(report.pk)
    return report


def set_practice_done(user, report_id: int, index: int, done: bool) -> bool:
    """Tick a practice item on or off. Returns False if there is no such item."""
    report = report_repository.get_report_for_user(user, report_id)
    plan = report_repository.get_training_plan(report) if report else None
    if plan is None or not 0 <= index < len(plan.tasks):
        return False
    report_repository.set_task_done(plan, index, done)
    return True


def list_reports(user):
    return report_repository.list_reports_for_user(user)


def get_report_with_plan(user, report_id: int) -> dict | None:
    """A report and its practice plan, or None if the user has no such report."""
    report = report_repository.get_report_for_user(user, report_id)
    if report is None:
        return None
    return {"report": report, "plan": report_repository.get_training_plan(report)}


def get_report(user, report_id: int) -> WeaknessReport | None:
    recover_stuck_reports(user)
    return report_repository.get_report_for_user(user, report_id)


def get_report_detail(user, report_id: int) -> dict | None:
    recover_stuck_reports(user)
    report = report_repository.get_report_for_user(user, report_id)
    if report is None:
        return None

    cited = {gid for w in report.weaknesses for gid in w.get("example_game_ids", [])}
    games = {g.pk: g for g in game_repository.get_games_for_user(user, cited)}
    weaknesses = [
        {**w, "games": [games[gid] for gid in w.get("example_game_ids", []) if gid in games]}
        for w in report.weaknesses
    ]
    return {
        "report": report,
        "report_games": report_repository.list_report_games(report),
        "weaknesses": weaknesses,
        "plan": report_repository.get_training_plan(report),
        "in_progress": report.status in (WeaknessReport.Status.QUEUED, WeaknessReport.Status.RUNNING),
        "total_tokens": report.input_tokens + report.output_tokens,
    }