import time

from django.core.management.base import BaseCommand, CommandError

from apps.games.models import Game
from apps.games.services.analysis_service import analyse_game


class Command(BaseCommand):
    help = "Analyse a stored game with Stockfish and save move evaluations and mistakes."

    def add_arguments(self, parser):
        parser.add_argument("game_id", type=int)
        parser.add_argument("--depth", type=int, default=None, help="Override STOCKFISH_DEPTH")

    def handle(self, *args, **options):
        start = time.perf_counter()
        try:
            summary = analyse_game(options["game_id"], depth=options["depth"])
        except Game.DoesNotExist:
            raise CommandError(f"No game with id {options['game_id']}")
        seconds = time.perf_counter() - start
        self.stdout.write(self.style.SUCCESS(
            f"Analysed {summary['moves']} moves, found {summary['mistakes']} mistakes "
            f"in {seconds:.1f} s"
        ))