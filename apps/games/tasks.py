from django.tasks import task

from apps.games.services.analysis_service import analyse_game


@task()
def analyse_game_task(game_id: int) -> dict:
    # Runs in the worker process (python manage.py db_worker), not in the web request.
    return analyse_game(game_id)