from django.tasks import task

from apps.coaching.services.diagnosis_service import run_report


@task()
def generate_report_task(report_id: int) -> None:
    # Runs in the worker process (python manage.py db_worker), not in the web request.
    run_report(report_id)