from apps.coaching.models import TrainingPlan, WeaknessReport


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
    return WeaknessReport.objects.filter(
        user=user, status__in=[WeaknessReport.Status.QUEUED, WeaknessReport.Status.RUNNING]
    ).exists()


def set_status(report: WeaknessReport, status: str, error: str = "") -> None:
    report.status = status
    report.error = error[:200]
    report.save(update_fields=["status", "error"])


def save_result(report: WeaknessReport, **fields) -> None:
    """Store the agent's answer and mark the report as done."""
    for name, value in fields.items():
        setattr(report, name, value)
    report.status = WeaknessReport.Status.DONE
    report.error = ""
    report.save()


def save_training_plan(report: WeaknessReport, tasks: list) -> TrainingPlan:
    plan, _ = TrainingPlan.objects.update_or_create(report=report, defaults={"tasks": tasks})
    return plan


def get_training_plan(report: WeaknessReport) -> TrainingPlan | None:
    return TrainingPlan.objects.filter(report=report).first()


def set_task_done(plan: TrainingPlan, index: int, done: bool) -> None:
    plan.tasks[index]["done"] = done
    plan.save(update_fields=["tasks"])
