"""Coach evaluation: runs the AI coach several times on the same games and measures
latency, tokens, cost, guardrail rejections and how well the evidence is grounded.

Started with:  python manage.py evaluate_coach <username> --runs 5 --games 5

Grounding: every move the coach cites in a weakness's evidence is checked against the
player's data with the same rules as the guardrail (ai/crews/diagnosis_crew/evidence.py).
Because the guardrail rejects invented moves, accepted reports should score 100%; the
rejections show how often the model invented something before it was corrected.
"""
import csv
import statistics
from pathlib import Path

from ai.crews.diagnosis_crew.evidence import KnownMoves
from ai.flows.coaching_flow import CoachingError, run_coaching
from evaluation.measure_latency import stopwatch

# Dollars per million input / output tokens (the same prices as in the README).
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
REJECTION_KINDS = {
    "structure": "does not match the required structure",
    "unknown_games": "cites games that are not in the data",
    "invented_moves": "cites moves that are not in the player's data",
}

RUN_COLUMNS = [
    "run", "success", "error", "seconds", "turns", "tool_calls", "tool_errors",
    "input_tokens", "output_tokens", "cost_usd", "rejections",
    *(f"{kind}_rejections" for kind in REJECTION_KINDS),
    "weaknesses", "weaknesses_citing_moves", "cited_moves", "grounded_moves", "grounding_pct",
]
RUBRIC_COLUMNS = [
    "run", "priority", "category", "title", "evidence", "explanation", "how_to_improve",
    "relevant", "specific", "correct",
]


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Price of one report, or None for a model that is not in PRICES."""
    prices = PRICES.get(model.rsplit("/", 1)[-1])
    if prices is None:
        return None
    return round((input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000, 4)


def rejection_counts(rejections: list[str]) -> dict:
    return {
        f"{kind}_rejections": sum(text in reason for reason in rejections)
        for kind, text in REJECTION_KINDS.items()
    }


def grounding(weaknesses: list[dict], known: KnownMoves) -> dict:
    """How many cited moves really appear in the player's data (played or engine best moves)."""
    cited = [known.cited_moves(w["evidence"]) for w in weaknesses]
    total = sum(len(moves) for moves in cited)
    grounded = sum(is_known for moves in cited for _, is_known in moves)
    return {
        "weaknesses_citing_moves": sum(1 for moves in cited if moves),
        "cited_moves": total,
        "grounded_moves": grounded,
        "grounding_pct": round(100 * grounded / total, 1) if total else None,
    }


def evaluate_run(number: int, records, llm, player: dict | None = None) -> tuple[dict, list[dict]]:
    """Run the coach once: (one CSV row, one rubric row per weakness)."""
    error = result = None
    with stopwatch() as watch:
        try:
            result = run_coaching(records, llm, player=player)
        except CoachingError as exc:
            error = exc

    row = {"run": number, "success": error is None, "seconds": watch["seconds"]}
    if error is not None:
        row.update(error=str(error), rejections=len(error.rejections), **rejection_counts(error.rejections))
        return row, []

    row.update(
        error="",
        turns=result.turns,
        tool_calls=len(result.tool_calls),
        tool_errors=sum(call.is_error for call in result.tool_calls),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost_usd(result.model, result.input_tokens, result.output_tokens),
        rejections=len(result.rejections),
        **rejection_counts(result.rejections),
        weaknesses=len(result.weaknesses),
        **grounding(result.weaknesses, KnownMoves.from_records(records)),
    )
    rubric = [{"run": number, **{key: w[key] for key in RUBRIC_COLUMNS[1:7]}} for w in result.weaknesses]
    return row, rubric


def write_csv(rows: list[dict], path, columns: list[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _mean(values, digits: int = 2) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), digits) if values else None


def summarize(rows: list[dict]) -> dict:
    """Totals and averages over all runs; tokens, cost and grounding over the successful ones."""
    done = [row for row in rows if row["success"]]
    seconds = [row["seconds"] for row in rows]
    cited = sum(row["cited_moves"] for row in done)
    grounded = sum(row["grounded_moves"] for row in done)
    costs = [row["cost_usd"] for row in done if row["cost_usd"] is not None]
    return {
        "runs": len(rows),
        "successes": len(done),
        "mean_seconds": _mean(seconds),
        "median_seconds": round(statistics.median(seconds), 2) if seconds else None,
        "max_seconds": round(max(seconds), 2) if seconds else None,
        "mean_input_tokens": _mean((row["input_tokens"] for row in done), digits=0),
        "mean_output_tokens": _mean((row["output_tokens"] for row in done), digits=0),
        "mean_turns": _mean((row["turns"] for row in done), digits=1),
        "mean_tool_calls": _mean((row["tool_calls"] for row in done), digits=1),
        "mean_cost_usd": _mean(costs, digits=4),
        "total_cost_usd": round(sum(costs), 4) if costs else None,
        "rejections": sum(row["rejections"] for row in rows),
        "runs_with_rejections": sum(1 for row in rows if row["rejections"]),
        **{key: sum(row[key] for row in rows) for key in rejection_counts([])},
        "mean_weaknesses": _mean((row["weaknesses"] for row in done), digits=1),
        "weaknesses_citing_moves": sum(row["weaknesses_citing_moves"] for row in done),
        "weaknesses": sum(row["weaknesses"] for row in done),
        "cited_moves": cited,
        "grounded_moves": grounded,
        "grounding_pct": round(100 * grounded / cited, 1) if cited else None,
        "errors": [row["error"] for row in rows if not row["success"]],
    }


def format_summary(s: dict, model: str, games: int, moves: int) -> str:
    """Plain-text summary for the terminal and the report."""
    lines = [
        f"Coach evaluation: {s['runs']} runs with {model} on the same {games} games ({moves} moves)",
        f"  Success : {s['successes']}/{s['runs']} runs ended with an accepted report",
        f"  Latency : mean {s['mean_seconds']} s, median {s['median_seconds']} s, max {s['max_seconds']} s per report",
        f"  Tokens  : mean {s['mean_input_tokens']} input and {s['mean_output_tokens']} output per report, "
        f"{s['mean_turns']} model requests and {s['mean_tool_calls']} tool calls",
        f"  Cost    : mean ${s['mean_cost_usd']} per report, ${s['total_cost_usd']} in total",
        f"  Guardrail: {s['rejections']} rejections in {s['runs_with_rejections']} of {s['runs']} runs "
        f"(structure {s['structure_rejections']}, unknown games {s['unknown_games_rejections']}, "
        f"invented moves {s['invented_moves_rejections']}); each rejection is one retry",
        f"  Grounding: {s['grounded_moves']}/{s['cited_moves']} cited moves are in the player's data "
        f"({s['grounding_pct']}%); {s['weaknesses_citing_moves']}/{s['weaknesses']} weaknesses cite at least "
        f"one move; {s['mean_weaknesses']} weaknesses per report",
    ]
    lines += [f"  Failed run: {error}" for error in s["errors"]]
    lines += [
        "",
        "Manual rubric: score each weakness in the rubric CSV from 1 (poor) to 5 (excellent):",
        "  relevant = it matters for this player's results",
        "  specific = it points to concrete positions, moves or habits, not general advice",
        "  correct  = the explanation and the evidence agree with the games",
        "",
    ]
    return "\n".join(lines)