"""Statistics over a player's analysed moves, for the coaching agents.

Pure Python, no Django: the coaching service turns database rows into
MoveRecord objects and passes them in. Every function returns plain
dicts/lists of numbers and strings, so the result can be sent to an
AI model as JSON.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

import chess

SEVERITIES = ("inaccuracy", "mistake", "blunder")
# Chess.com-style move types (see ai/engine/move_types.py), best first.
MOVE_TYPES = ("brilliant", "great", "best", "excellent", "good", "miss", "inaccuracy", "mistake", "blunder")
PHASES = ("opening", "middlegame", "endgame")


@dataclass(frozen=True)
class MoveRecord:
    """One move played by the player being coached."""

    game_id: int
    ply: int
    san: str
    fen_before: str
    phase: str
    cp_loss: int
    severity: str = ""  # "" when the move was fine
    motif: str = ""
    opening: str = ""
    best_move_uci: str = ""
    label: str = ""  # move type, e.g. "great"; "" for games analysed before move types existed


def _average(values) -> float | None:
    values = list(values)
    return round(sum(values) / len(values), 1) if values else None


def _per_100(count: int, moves: int) -> float:
    return round(100 * count / moves, 1) if moves else 0.0


def summarize_mistakes(records: list[MoveRecord]) -> dict:
    """Overall picture: how often and where the player makes mistakes."""
    labelled = [r for r in records if r.severity]

    by_phase = {}
    for phase in PHASES:
        moves = [r for r in records if r.phase == phase]
        mistakes = [r for r in moves if r.severity]
        by_phase[phase] = {
            "moves": len(moves),
            "mistakes": len(mistakes),
            "blunders": sum(1 for r in mistakes if r.severity == "blunder"),
            "mistakes_per_100_moves": _per_100(len(mistakes), len(moves)),
            "avg_cp_loss": _average(r.cp_loss for r in moves),
        }

    motif_counts = Counter(r.motif for r in labelled if r.motif)
    return {
        "games": len({r.game_id for r in records}),
        "moves": len(records),
        "avg_cp_loss": _average(r.cp_loss for r in records),
        "by_severity": {s: sum(1 for r in labelled if r.severity == s) for s in SEVERITIES},
        "by_phase": by_phase,
        "by_motif": dict(motif_counts.most_common()),
        "unexplained_mistakes": sum(1 for r in labelled if not r.motif),
        # Good moves too, so the coach can say what the player does well.
        "move_types": {t: sum(1 for r in records if r.label == t) for t in MOVE_TYPES},
    }


def opening_breakdown(records: list[MoveRecord], min_games: int = 1) -> list[dict]:
    """Results per opening, worst average centipawn loss first."""
    groups = defaultdict(list)
    for record in records:
        groups[record.opening or "Unknown opening"].append(record)

    rows = []
    for opening, moves in groups.items():
        games = len({r.game_id for r in moves})
        if games < min_games:
            continue
        opening_moves = [r for r in moves if r.phase == "opening"]
        rows.append({
            "opening": opening,
            "games": games,
            "mistakes": sum(1 for r in moves if r.severity),
            "opening_phase_mistakes": sum(1 for r in opening_moves if r.severity),
            "avg_cp_loss": _average(r.cp_loss for r in moves),
        })
    return sorted(rows, key=lambda row: row["avg_cp_loss"] or 0, reverse=True)

def best_move_san(fen_before: str, best_uci: str) -> str:
    """The engine's best move in normal notation (e.g. "Bxf7"), so the AI never has to translate it."""
    if not best_uci:
        return ""
    try:
        board = chess.Board(fen_before)
        return board.san(chess.Move.from_uci(best_uci))
    except ValueError:
        return ""


def worst_moves(records: list[MoveRecord], limit: int = 5, motif: str = "", phase: str = "") -> list[dict]:
    """The costliest mistakes, as concrete evidence (with the position as FEN)."""
    candidates = [
        r for r in records
        if r.severity and (not motif or r.motif == motif) and (not phase or r.phase == phase)
    ]
    candidates.sort(key=lambda r: r.cp_loss, reverse=True)
    return [
        {
            "game_id": r.game_id,
            "move": f"{(r.ply + 1) // 2}{'.' if r.ply % 2 else '...'} {r.san}",
            "severity": r.severity,
            "phase": r.phase,
            "motif": r.motif,
            "cp_loss": r.cp_loss,
            "best_move": best_move_san(r.fen_before, r.best_move_uci),
            "fen_before": r.fen_before,
        }
        for r in candidates[:limit]
    ]


def opening_label(headers: dict, sans: list[str]) -> str:
    """A readable opening name: the PGN's Opening/ECO header, else the first moves."""
    opening = headers.get("Opening", "")
    if opening and opening != "?":
        return opening
    eco = headers.get("ECO", "")
    if eco and eco != "?":
        return f"ECO {eco}"
    first = []
    for i, san in enumerate(sans[:6]):
        first.append(f"{i // 2 + 1}. {san}" if i % 2 == 0 else san)
    return " ".join(first) if first else ""