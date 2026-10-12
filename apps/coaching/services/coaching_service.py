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
        "ready_games": game_repository.list_games_for_coaching(user),
        "reports": report_repository.list_reports_for_user(user),
    }


def _parse_ids(game_ids) -> set[int]:
    try:
        return {int(game_id) for game_id in game_ids}
    except (TypeError, ValueError):
        raise CoachingError("Invalid game selection.")


def request_report(user, game_ids) -> WeaknessReport:
    """Queue a new report (weaknesses + training plan) for the chosen games."""
    chosen = _parse_ids(game_ids)
    if not chosen:
        raise CoachingError("Choose at least one game for the coach to study.")
    games = list(game_repository.get_ready_games(user, chosen))
    if len(games) != len(chosen):
        raise CoachingError(
            "Some chosen games are not ready: they must be analysed and have your side set."
        )
    if report_repository.has_report_in_progress(user):
        raise CoachingError("A report is already being prepared.")

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
        "report_games": report_repository.list_report_games(report),
        "weaknesses": weaknesses,
        "plan": report_repository.get_training_plan(report),
        "in_progress": report.status in (WeaknessReport.Status.QUEUED, WeaknessReport.Status.RUNNING),
        "total_tokens": report.input_tokens + report.output_tokens,
    }