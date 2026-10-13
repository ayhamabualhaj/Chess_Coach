"""Diagnosis agent: finds a player's recurring weaknesses with Claude and tool use,
and explains how to fix each one.

The agent is a loop, not a single API call. Claude gets a short description
of the player and a set of tools over their analysed moves (the functions in
ai/tools). It decides which statistics to look at, asks for concrete example
positions, and finishes by calling `submit_diagnosis` with a structured list
of weaknesses, each with how to improve and exercises. Every weakness must cite
games that really exist in the data; if not, the tool returns an error and
Claude has to fix it. (The puzzle practice list is built by code from the
mistakes themselves, see ai/tools/practice_tools.py.)

Pure Python, no Django: the caller passes in MoveRecord objects and,
optionally, an Anthropic client (tests pass a fake one).

Sources: Anthropic Python SDK (https://github.com/anthropics/anthropic-sdk-python),
Claude tool use docs (manual agentic loop, strict tools, tool_result with is_error),
refusals and fallback (https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback).
"""
import json
import time
from dataclasses import dataclass, field

import anthropic
import chess

from ai.tools.motif_tools import detect_motifs
from ai.tools.stats_tools import PHASES, MoveRecord, opening_breakdown, summarize_mistakes, worst_moves

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TURNS = 8
MAX_WORST_MOVES = 10

CATEGORIES = ("tactics", "opening", "middlegame", "endgame", "time_or_focus", "other")
MOTIFS = (
    "", "allowed_mate", "missed_mate", "hanging_piece", "missed_fork",
    "missed_capture", "missed_check", "allowed_forced_mate", "missed_forced_mate",
)

SYSTEM_PROMPT = """You are a chess coach. You study engine analysis of one player's games, find \
their 2-4 most important recurring weaknesses, and tell them exactly how to fix each one.

How to work:
- Start with get_mistake_summary, then look at whatever else you need (openings, worst moves, \
single positions). Each tool call costs time, so stop once the picture is clear.
- A weakness must be a pattern (it repeats across moves or games), not a single bad move. \
If only one game is analysed, say that the patterns are tentative.
- Back every weakness with evidence from the tool results: numbers and concrete moves with their \
game ids. Use the moves exactly as the tools give them (e.g. best_move "Bxf7"); never convert or \
invent moves, games or statistics.
- Centipawn loss (cp_loss) is measured by Stockfish; motifs come from simple board rules, so \
"unexplained" mistakes are possible.
- get_mistake_summary also counts move types (brilliant, great, best, excellent, good, miss, ...). \
In the summary, name one real strength when these numbers show one (e.g. several great moves).

For each weakness, also give the cure:
- how_to_improve: what to change in the player's thinking or habits, concretely.
- exercises: 2-3 practical exercises or habits. The app already links puzzle sets for each \
mistake type, so focus on other practice (reviewing own games, thinking routines, slower games). \
Match the advice to the player's rating when it is given.

Write for the player: clear, encouraging, no jargon without explanation.
When you are done, call submit_diagnosis exactly once. Do not write the diagnosis as plain text."""

TOOLS = [
    {
        "name": "get_mistake_summary",
        "description": (
            "Overall statistics for the player: number of games and moves, average centipawn loss, "
            "mistakes by severity, by game phase (opening/middlegame/endgame) and by tactical motif, "
            "and how many moves of each type (brilliant, great, best, excellent, good, miss, ...)."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "get_opening_breakdown",
        "description": (
            "Results per opening, worst average centipawn loss first. min_games skips openings "
            "played fewer times (use 1 to see all)."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"min_games": {"type": "integer", "description": "At least 1."}},
            "required": ["min_games"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_worst_moves",
        "description": (
            "The costliest mistakes as concrete examples (game id, move, motif, cp_loss, best move, "
            "position as FEN). Optionally filter by motif and/or phase; use \"\" for no filter."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": f"1 to {MAX_WORST_MOVES}."},
                "motif": {"type": "string", "enum": list(MOTIFS)},
                "phase": {"type": "string", "enum": ["", *PHASES]},
            },
            "required": ["limit", "motif", "phase"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explain_position",
        "description": (
            "Re-check one position with the tactical pattern rules: which motifs explain why the "
            "played move was worse than the best move. Give the moves in normal notation "
            "exactly as get_worst_moves returned them, e.g. played 'Qxf7+' and best 'Bxf7'."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "fen_before": {"type": "string"},
                "played_move": {"type": "string"},
                "best_move": {"type": "string"},
            },
            "required": ["fen_before", "played_move", "best_move"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_diagnosis",
        "description": "Submit the final diagnosis. Call this once, at the end.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "2-4 sentences about the player overall."},
                "weaknesses": {
                    "type": "array",
                    "description": "Most important first.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Short name, e.g. 'Leaving pieces undefended'."},
                            "category": {"type": "string", "enum": list(CATEGORIES)},
                            "explanation": {"type": "string", "description": "What goes wrong and why it matters."},
                            "evidence": {"type": "string", "description": "Numbers and example moves from the tools."},
                            "example_game_ids": {"type": "array", "items": {"type": "integer"}},
                            "priority": {"type": "integer", "description": "1 = work on this first, 3 = least urgent."},
                            "how_to_improve": {"type": "string", "description": "Concrete change of habit or thinking."},
                            "exercises": {
                                "type": "array",
                                "description": "2-3 practical exercises.",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "title", "category", "explanation", "evidence", "example_game_ids",
                            "priority", "how_to_improve", "exercises",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "weaknesses"],
            "additionalProperties": False,
        },
    },
]


class DiagnosisError(Exception):
    """The agent could not produce a diagnosis (no data, API error, refusal, too many turns)."""


@dataclass
class ToolCall:
    """One step of the agent, kept for the UI and the performance report."""

    name: str
    input: dict
    seconds: float
    is_error: bool = False


@dataclass
class DiagnosisResult:
    summary: str
    weaknesses: list[dict]
    model: str
    turns: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


class _Toolbox:
    """Runs the tools Claude asks for, over one player's records."""

    def __init__(self, records: list[MoveRecord]):
        self.records = records
        self.game_ids = {r.game_id for r in records}

    def run(self, name: str, args: dict):
        """Returns the tool result (JSON-serialisable). Raises ValueError for bad input."""
        if name == "get_mistake_summary":
            return summarize_mistakes(self.records)
        if name == "get_opening_breakdown":
            return opening_breakdown(self.records, min_games=max(1, int(args.get("min_games", 1))))
        if name == "get_worst_moves":
            limit = min(max(1, int(args.get("limit", 5))), MAX_WORST_MOVES)
            return worst_moves(self.records, limit=limit, motif=args.get("motif", ""), phase=args.get("phase", ""))
        if name == "explain_position":
            try:
                board = chess.Board(args["fen_before"])
                played = board.parse_san(args["played_move"]).uci()
                best = board.parse_san(args["best_move"]).uci() if args.get("best_move") else ""
                return {"motifs": detect_motifs(args["fen_before"], played, best)}
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Invalid position or move: {exc}") from exc
        raise ValueError(f"Unknown tool: {name}")

    def check_diagnosis(self, args: dict) -> list[dict]:
        """Validates submit_diagnosis input and returns the cleaned weaknesses."""
        weaknesses = args.get("weaknesses") or []
        if not args.get("summary") or not weaknesses:
            raise ValueError("Give a summary and at least one weakness.")
        cleaned = []
        for weakness in weaknesses:
            unknown = set(weakness.get("example_game_ids", [])) - self.game_ids
            if unknown:
                raise ValueError(
                    f"Weakness '{weakness.get('title')}' cites games that are not in the data: "
                    f"{sorted(unknown)}. Only use game ids returned by the tools."
                )
            if weakness.get("category") not in CATEGORIES:
                raise ValueError(f"Unknown category: {weakness.get('category')}")
            if not weakness.get("how_to_improve") or not weakness.get("exercises"):
                raise ValueError(f"Weakness '{weakness.get('title')}' needs how_to_improve and exercises.")
            cleaned.append({**weakness, "priority": min(max(1, int(weakness.get("priority", 2))), 3)})
        return sorted(cleaned, key=lambda w: w["priority"])


def _player_prompt(records: list[MoveRecord], player: dict | None) -> str:
    player = player or {}
    lines = ["Diagnose this player's recurring weaknesses and explain how to fix them."]
    if player.get("name"):
        lines.append(f"Player: {player['name']}")
    if player.get("rating"):
        lines.append(f"Rating: {player['rating']}")
    lines.append(f"Analysed: {len({r.game_id for r in records})} games, {len(records)} of their moves.")
    return "\n".join(lines)


class DiagnosisAgent:
    def __init__(self, client=None, model: str = DEFAULT_MODEL, max_turns: int = MAX_TURNS):
        self.client = client
        self.model = model
        self.max_turns = max_turns

    def _create(self, messages: list):
        extra = {}
        if not self.model.startswith("claude-haiku"):
            # Server-side fallback: if a safety classifier declines the request,
            # the API re-runs it on Anthropic's recommended fallback model.
            # Claude Haiku 5.5 has no server-side fallback, so it is not sent there.
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_choice={"type": "auto"},
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            messages=messages,
            **extra,
        )

    def run(self, records: list[MoveRecord], player: dict | None = None) -> DiagnosisResult:
        if not records:
            raise DiagnosisError("No analysed moves yet. Analyse some games first.")
        if self.client is None:
            self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

        toolbox = _Toolbox(records)
        messages = [{"role": "user", "content": _player_prompt(records, player)}]
        result = DiagnosisResult(summary="", weaknesses=[], model=self.model, turns=0)
        started = time.perf_counter()
        nudged = False

        for _ in range(self.max_turns):
            try:
                response = self._create(messages)
            except anthropic.AnthropicError as exc:
                raise DiagnosisError(f"AI service error: {exc}") from exc
            result.turns += 1
            result.model = response.model
            usage = response.usage
            # Cached prompt tokens are reported separately from input_tokens.
            result.input_tokens += (
                usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
            )
            result.output_tokens += usage.output_tokens

            if response.stop_reason == "refusal":
                raise DiagnosisError("The AI model declined this request.")
            if response.stop_reason == "max_tokens":
                raise DiagnosisError("The AI response was cut off (max_tokens).")

            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            if not tool_uses:
                # Claude answered in text instead of submitting: remind it once.
                if nudged:
                    raise DiagnosisError("The agent finished without submitting a diagnosis.")
                nudged = True
                messages.append({"role": "user", "content": "Please call submit_diagnosis with your findings."})
                continue

            tool_results = []
            for block in tool_uses:
                tool_started = time.perf_counter()
                is_error = False
                try:
                    if block.name == "submit_diagnosis":
                        weaknesses = toolbox.check_diagnosis(block.input)
                        result.tool_calls.append(ToolCall(block.name, block.input, time.perf_counter() - tool_started))
                        result.summary = block.input["summary"]
                        result.weaknesses = weaknesses
                        result.seconds = time.perf_counter() - started
                        return result
                    content = json.dumps(toolbox.run(block.name, block.input))
                except ValueError as exc:
                    is_error = True
                    content = str(exc)
                result.tool_calls.append(ToolCall(block.name, block.input, time.perf_counter() - tool_started, is_error))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                })
            # All results go back together in one user message.
            messages.append({"role": "user", "content": tool_results})

        raise DiagnosisError(f"No diagnosis after {self.max_turns} turns.")