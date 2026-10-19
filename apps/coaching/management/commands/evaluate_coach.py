from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.coaching.services import diagnosis_service
from evaluation.measure_coaching import RUBRIC_COLUMNS, RUN_COLUMNS, evaluate_run, format_summary, summarize, write_csv


class Command(BaseCommand):
    help = (
        "Coach evaluation: run the AI coach several times on the same games of one user and report "
        "latency, tokens, cost, guardrail rejections and grounding. Uses the real AI model (costs money)."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", help="The user whose analysed games the coach studies")
        parser.add_argument("--runs", type=int, default=5, help="How many reports to generate")
        parser.add_argument("--games", type=int, default=5, help="Use the user's N latest games that are ready for coaching")
        parser.add_argument("--out", default="docs/coach_evaluation.csv", help="CSV file, one row per run")

    def handle(self, *args, **options):
        if not settings.AI_API_KEY:
            raise CommandError("No AI_API_KEY found in .env.")
        if options["runs"] < 1 or options["games"] < 1:
            raise CommandError("--runs and --games must be at least 1.")
        inputs = diagnosis_service.evaluation_inputs(options["username"], options["games"])
        if inputs is None:
            raise CommandError(f"No user called '{options['username']}'.")
        if not inputs["records"]:
            raise CommandError("This user has no games that are analysed and have their side set.")

        rows, rubric = [], []
        for number in range(1, options["runs"] + 1):
            # A new LLM for every run: CrewAI's LLM keeps a running total of the tokens it has used.
            llm = inputs["make_llm"]()
            row, weaknesses = evaluate_run(number, inputs["records"], llm, inputs["player"])
            rows.append(row)
            rubric += weaknesses
            outcome = f"{row['weaknesses']} weaknesses, ${row['cost_usd']}" if row["success"] else row["error"]
            self.stdout.write(
                f"run {number}/{options['runs']}: {row['seconds']} s, {row['rejections']} rejections, {outcome}"
            )

        out = Path(options["out"])
        write_csv(rows, out, RUN_COLUMNS)
        rubric_path = out.with_name(out.stem + "_rubric.csv")
        write_csv(rubric, rubric_path, RUBRIC_COLUMNS)
        model = getattr(llm, "model", settings.AI_MODEL)
        text = format_summary(summarize(rows), model, inputs["games"], len(inputs["records"]))
        summary_path = out.with_suffix(".txt")
        summary_path.write_text(text, encoding="utf-8")
        self.stdout.write("\n" + text)
        self.stdout.write(self.style.SUCCESS(f"Saved {out}, {summary_path} and {rubric_path}"))