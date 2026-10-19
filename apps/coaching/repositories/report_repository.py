from django.utils import timezone

from apps.coaching.models import TrainingPlan, WeaknessReport

IN_PROGRESS = (WeaknessReport.Status.QUEUED, WeaknessReport.Status.RUNNING)


def create_report(user, games) -> WeaknessReport:
    report = WeaknessReport.objects.create(user=user)
    report.games.set(games)
    return report


def list_report_games(report: WeaknessReport):
    return report.games.all()


def get_report(report_id: int) -> WeaknessReport:
    return WeaknessReport.objects.select_related("user").get(pk=report_id)


def get_report_for_user(user, report_id: int) -> WeaknessReport | None:
    return WeaknessReport.objects.filter(user=user, pk=report_id).first()


def list_reports_for_user(user):
    return WeaknessReport.objects.filter(user=user)


def has_report_in_progress(user) -> bool:
    return WeaknessReport.objects.filter(user=user, status__in=IN_PROGRESS).exists()

def count_reports_since(user, since) -> int:
    return WeaknessReport.objects.filter(user=user, created_at__gte=since).count()

def fail_stuck_reports(older_than, message: str, user=None) -> int:
    """Mark reports waiting or running since before `older_than` as failed; returns how many."""
    reports = WeaknessReport.objects.filter(status__in=IN_PROGRESS, status_changed_at__lt=older_than)
    if user is not None:
        reports = reports.filter(user=user)
    return reports.update(status=WeaknessReport.Status.FAILED, error=message[:200], status_changed_at=timezone.now())


def set_status(report: WeaknessReport, status: str, error: str = "") -> None:
    report.status = status
    report.error = error[:200]
    report.status_changed_at = timezone.now()
    report.save(update_fields=["status", "error", "status_changed_at"])


def save_result(report: WeaknessReport, **fields) -> None:
    """Store the agent's answer and mark the report as done."""
    for name, value in fields.items():
        setattr(report, name, value)
    report.status = WeaknessReport.Status.DONE
    report.error = ""
    report.status_changed_at = timezone.now()
    report.save()


def save_training_plan(report: WeaknessReport, tasks: list) -> TrainingPlan:
    plan, _ = TrainingPlan.objects.update_or_create(report=report, defaults={"tasks": tasks})
    return plan


def get_training_plan(report: WeaknessReport) -> TrainingPlan | None:
    return TrainingPlan.objects.filter(report=report).first()


def set_task_done(plan: TrainingPlan, index: int, done: bool) -> None:
    plan.tasks[index]["done"] = done
    plan.save(update_fields=["tasks"])