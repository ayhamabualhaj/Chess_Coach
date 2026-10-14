import json
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import chess
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai.tools.motif_tools import detect_motifs
from ai.tools.stats_tools import MoveRecord, opening_breakdown, summarize_mistakes, worst_moves

MAX_WORST_MOVES = 10

Motif = Literal[
    "", "allowed_mate", "missed_mate", "hanging_piece", "missed_fork",
    "missed_capture", "missed_check", "allowed_forced_mate", "missed_forced_mate",
]
Phase = Literal["", "opening", "middlegame", "endgame"]


@dataclass
class ToolCall:
    name: str
    input: dict
    seconds: float
    is_error: bool = False


@dataclass
class CoachData:
    records: list[MoveRecord]
    calls: list[ToolCall] = field(default_factory=list)

    @property
    def game_ids(self) -> set[int]:
        return {r.game_id for r in self.records}


class CoachTool(BaseTool):
    data: CoachData = Field(exclude=True)

    def _run(self, **kwargs) -> str:
        started = time.perf_counter()
        try:
            result = json.dumps(self.compute(**kwargs))
            is_error = False
        except ValueError as exc:
            result = f"Error: {exc}"
            is_error = True
        self.data.calls.append(ToolCall(self.name, kwargs, time.perf_counter() - started, is_error))
        return result

    @abstractmethod
    def compute(self, **kwargs):
        raise NotImplementedError


class NoInput(BaseModel):
    pass


class MistakeSummaryTool(CoachTool):
    name: str = "get_mistake_summary"
    description: str = (
        "Overall statistics for the player: number of games and moves, average centipawn loss, "
        "mistakes by severity, by game phase (opening/middlegame/endgame) and by tactical motif, "
        "and how many moves of each type (brilliant, great, best, excellent, good, miss, ...)."
    )
    args_schema: type[BaseModel] = NoInput

    def compute(self):
        return summarize_mistakes(self.data.records)


class OpeningInput(BaseModel):
    min_games: int = Field(1, ge=1, description="Skip openings played fewer times (1 = show all).")


class OpeningBreakdownTool(CoachTool):
    name: str = "get_opening_breakdown"
    description: str = "Results per opening, worst average centipawn loss first."
    args_schema: type[BaseModel] = OpeningInput

    def compute(self, min_games: int = 1):
        return opening_breakdown(self.data.records, min_games=min_games)


class WorstMovesInput(BaseModel):
    limit: int = Field(5, ge=1, le=MAX_WORST_MOVES, description=f"1 to {MAX_WORST_MOVES}.")
    motif: Motif = Field("", description='Only this motif; "" for all.')
    phase: Phase = Field("", description='Only this game phase; "" for all.')


class WorstMovesTool(CoachTool):
    name: str = "get_worst_moves"
    description: str = (
        "The costliest mistakes as concrete examples (game id, move, motif, cp_loss, best move, "
        "position as FEN). Optionally filter by motif and/or phase."
    )
    args_schema: type[BaseModel] = WorstMovesInput

    def compute(self, limit: int = 5, motif: str = "", phase: str = ""):
        return worst_moves(self.data.records, limit=limit, motif=motif, phase=phase)


class PositionInput(BaseModel):
    fen_before: str = Field(description="The position before the move, as FEN.")
    played_move: str = Field(description="The move that was played, e.g. 'Qxf7+'.")
    best_move: str = Field(description="The engine's best move, e.g. 'Bxf7'.")


class ExplainPositionTool(CoachTool):
    name: str = "explain_position"
    description: str = (
        "Re-check one position with the tactical pattern rules: which motifs explain why the "
        "played move was worse than the best move. Give the moves exactly as get_worst_moves "
        "returned them."
    )
    args_schema: type[BaseModel] = PositionInput

    def compute(self, fen_before: str, played_move: str, best_move: str):
        try:
            board = chess.Board(fen_before)
            played = board.parse_san(played_move).uci()
            best = board.parse_san(best_move).uci() if best_move else ""
        except ValueError as exc:
            raise ValueError(f"Invalid position or move: {exc}") from exc
        return {"motifs": detect_motifs(fen_before, played, best)}


def make_tools(data: CoachData) -> list[CoachTool]:
    return [
        MistakeSummaryTool(data=data),
        OpeningBreakdownTool(data=data),
        WorstMovesTool(data=data),
        ExplainPositionTool(data=data),
    ]