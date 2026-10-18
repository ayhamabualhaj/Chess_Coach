from django.conf import settings
from django.core.management.base import BaseCommand

from apps.coaching.services import coaching_service
from apps.games.services import game_service


class Command(BaseCommand):
    help = "Mark analyses and reports that have been waiting or running too long as failed (e.g. after the worker stopped)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes", type=int, default=None,
            help=f"Treat jobs older than this as stuck (default: STUCK_JOB_MINUTES = {settings.STUCK_JOB_MINUTES}). "
                 "Use 0 right after restarting the worker.",
        )

    def handle(self, *args, **options):
        games = game_service.recover_stuck_games(minutes=options["minutes"])
        reports = coaching_service.recover_stuck_reports(minutes=options["minutes"])
        self.stdout.write(f"Marked {games} stuck game analyses and {reports} stuck reports as failed.")