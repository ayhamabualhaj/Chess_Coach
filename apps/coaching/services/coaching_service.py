from apps.coaching.models import WeaknessReport
from apps.coaching.repositories import report_repository
from apps.coaching.tasks import generate_report_task
from apps.games.repositories import game_repository


class CoachingError(Exception):
    pass


def get_overview(user) -> dict:
    """Everything the coaching page needs."""
    return {
        "games": game_repository.count_games_by_state(user),
        "reports": report_repository.list_reports_for_user(user),
    }


def request_report(user) -> WeaknessReport:
    """Queue a new weakness report for the user."""
    if game_repository.count_games_by_state(user)["ready"] == 0:
        raise CoachingError(
            "Analyse at least one game and say which side you played before asking for a report."
        )
    if report_repository.has_report_in_progress(user):
        raise CoachingError("A report is already being prepared.")
    report = report_repository.create_report(user)
    generate_report_task.enqueue(report.pk)
    return report


def get_report(user, report_id: int) -> WeaknessReport | None:
    return report_repository.get_report_for_user(user, report_id)


def get_report_detail(user, report_id: int) -> dict | None:
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
        "weaknesses": weaknesses,
        "in_progress": report.status in (WeaknessReport.Status.QUEUED, WeaknessReport.Status.RUNNING),
        "total_tokens": report.input_tokens + report.output_tokens,
    }