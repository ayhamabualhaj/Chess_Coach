from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from evaluation.run_evaluation import evaluate_game, format_summary, read_games, summarize, warm_up, write_csv


class Command(BaseCommand):
    help = (
        "Performance evaluation: run our analysis on Lichess-analysed games at one or more depths "
        "and report accuracy (vs Lichess labels), latency and memory per game."
    )

    def add_arguments(self, parser):
        parser.add_argument("pgn_files", nargs="+", help="PGN files exported from Lichess with computer analysis")
        parser.add_argument("--depths", type=int, nargs="+", default=[12, 18])
        parser.add_argument("--out", default="docs/evaluation_results.csv", help="CSV file, one row per game and depth")
        parser.add_argument("--limit", type=int, default=None, help="Use only the first N games")
        parser.add_argument("--repeat", type=int, default=1, help="Time each game N times and keep the median")
        parser.add_argument(
            "--great-overhead", action="store_true",
            help="Also run each game without the Great check to measure its extra time (twice as slow)",
        )

    def handle(self, *args, **options):
        missing = [path for path in options["pgn_files"] if not Path(path).exists()]
        if missing:
            raise CommandError(f"File not found: {', '.join(missing)}")
        games, skipped = read_games(options["pgn_files"])
        games = games[: options["limit"]]
        if not games:
            raise CommandError("No games with Lichess computer analysis found in these files.")
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {skipped} games without Lichess computer analysis."))

        warm_up()
        rows = []
        for depth in options["depths"]:
            for number, game in enumerate(games, start=1):
                row = evaluate_game(
                    game, number, depth, great_overhead=options["great_overhead"], repeats=options["repeat"]
                )
                rows.append(row)
                self.stdout.write(
                    f"depth {depth:>2} | game {number}/{len(games)} {row['game']}: {row['plies']} moves, "
                    f"{row['seconds']} s, F1 {row['f1']}"
                )

        write_csv(rows, options["out"])
        text = format_summary(summarize(rows))
        summary_path = Path(options["out"]).with_suffix(".txt")
        summary_path.write_text(text, encoding="utf-8")
        self.stdout.write("\n" + text)
        self.stdout.write(self.style.SUCCESS(f"Saved {options['out']} and {summary_path}"))
