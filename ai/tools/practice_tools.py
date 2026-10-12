"""Turns a player's mistakes into a practice list of Lichess puzzle sets.

Pure Python, no Django, no AI: the list comes straight from the analysed
mistakes, so every count and link is based on real data.

Lichess puzzle themes and URLs (lichess.org/training/<theme>) are taken from
Lichess's source code: lichess-org/lila, modules/puzzle/src/main/PuzzleTheme.scala
and the "/training/:angleOrId" route in conf/routes.
"""
from collections import defaultdict

from ai.tools.stats_tools import MoveRecord

LICHESS_TRAINING_URL = "https://lichess.org/training/{theme}"

PUZZLES_PER_MISTAKE = 3
MAX_PUZZLES_PER_THEME = 15

# Lichess theme key -> name shown to the player.
THEME_NAMES = {
    "hangingPiece": "Hanging pieces",
    "fork": "Forks",
    "mateIn1": "Mate in 1",
    "mateIn2": "Mate in 2",
    "short": "Short tactics",
    "opening": "Opening",
    "middlegame": "Middlegame",
    "endgame": "Endgame",
}

# Our tactical motif -> the Lichess theme that trains it.
MOTIF_TO_THEME = {
    "hanging_piece": "hangingPiece",
    "missed_capture": "hangingPiece",
    "missed_fork": "fork",
    "allowed_mate": "mateIn1",
    "missed_mate": "mateIn1",
    "allowed_forced_mate": "mateIn2",
    "missed_forced_mate": "mateIn2",
    "missed_check": "short",
}

# Mistakes without a motif are trained by game phase instead.
PHASE_TO_THEME = {"opening": "opening", "middlegame": "middlegame", "endgame": "endgame"}


def _theme_of(record: MoveRecord) -> str:
    return MOTIF_TO_THEME.get(record.motif) or PHASE_TO_THEME.get(record.phase, "short")


def _move_label(record: MoveRecord) -> str:
    number = (record.ply + 1) // 2
    return f"{number}{'.' if record.ply % 2 else '...'} {record.san}"


def build_practice(records: list[MoveRecord]) -> list[dict]:
    """One item per Lichess theme: 3 puzzles for each of the player's mistakes of that type.

    Returns dicts with theme, name, url, puzzles, mistakes, blunders, examples
    ([{"move", "game_id"}]) and done=False,
    most important (most mistakes, then most blunders) first.
    """
    groups = defaultdict(list)
    for record in records:
        if record.severity:
            groups[_theme_of(record)].append(record)

    items = []
    for theme, mistakes in groups.items():
        worst = sorted(mistakes, key=lambda r: r.cp_loss, reverse=True)
        items.append({
            "theme": theme,
            "name": THEME_NAMES[theme],
            "url": LICHESS_TRAINING_URL.format(theme=theme),
            "puzzles": min(PUZZLES_PER_MISTAKE * len(mistakes), MAX_PUZZLES_PER_THEME),
            "mistakes": len(mistakes),
            "blunders": sum(1 for r in mistakes if r.severity == "blunder"),
            "examples": [{"move": _move_label(r), "game_id": r.game_id} for r in worst[:3]],
            "done": False,
        })
    return sorted(items, key=lambda item: (item["mistakes"], item["blunders"]), reverse=True)