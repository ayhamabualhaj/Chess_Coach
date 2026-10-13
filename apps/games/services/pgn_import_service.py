import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date

import chess.pgn

from ai.tools import opening_label
from apps.accounts.repositories import account_repository
from apps.games.repositories import game_repository

PLAYED_AS_CHOICES = ("auto", "white", "black")
# Any number of games can be uploaded; this only stops absurdly large files.
MAX_PGN_BYTES = 5 * 1024 * 1024
MAX_ERRORS_SHOWN = 5

PGN_DATE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})$")


class InvalidPGNError(Exception):
    pass


@dataclass
class ImportResult:
    games: list = field(default_factory=list)  # the new Game objects
    duplicates: int = 0  # games that were already uploaded before
    errors: list[str] = field(default_factory=list)  # one line per skipped game


def _header(game, name: str) -> str:
    # PGN uses "?" for unknown values; store those as empty.
    value = game.headers.get(name, "")
    return "" if value in ("?", "*") else value


def _played_on(game) -> date | None:
    match = PGN_DATE.match(game.headers.get("UTCDate") or game.headers.get("Date", ""))
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def _opening(game) -> str:
    board = game.board()
    sans = []
    for move in list(game.mainline_moves())[:6]:
        sans.append(board.san(move))
        board.push(move)
    return opening_label(dict(game.headers), sans)[:200]


def _fingerprint(game, pgn_text: str) -> str:
    """The same game uploaded twice gets the same fingerprint: its Lichess or
    Chess.com link when the PGN has one, otherwise the PGN text itself."""
    link = next(
        (game.headers[name] for name in ("Link", "Site") if game.headers.get(name, "").startswith("http")),
        "",
    )
    return hashlib.sha256((link.strip().lower() or pgn_text).encode()).hexdigest()


def _user_names(user) -> set[str]:
    """The user's username and Lichess name, to recognise them in PGN headers."""
    profile = account_repository.get_profile(user)
    names = {user.username.lower()}
    if profile and profile.lichess_username:
        names.add(profile.lichess_username.lower())
    return names


def detect_user_color(user, white: str, black: str, names: set[str] | None = None) -> str:
    """Match the PGN player names against the user's username and Lichess name."""
    names = names if names is not None else _user_names(user)
    if white.lower() in names:
        return "white"
    if black.lower() in names:
        return "black"
    return ""


class _QuietGameBuilder(chess.pgn.GameBuilder):
    """Collects errors in game.errors without also logging them (python-chess docs,
    GameBuilder.handle_error): bad games are reported to the user instead."""

    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


def _read_games(pgn_text: str):
    """Yield (number, game) for every game in the text, in order."""
    stream = io.StringIO(pgn_text)
    number = 0
    while True:
        game = chess.pgn.read_game(stream, Visitor=_QuietGameBuilder)
        if game is None:
            return
        number += 1
        yield number, game


def import_pgn(user, pgn_text: str, played_as: str = "auto") -> ImportResult:
    """Save every game in the PGN text (one file can hold many games).

    Games with illegal moves or without moves are skipped and reported;
    games the user already uploaded are counted as duplicates.
    """
    pgn_text = pgn_text.strip()
    if not pgn_text:
        raise InvalidPGNError("Please paste a PGN or choose a .pgn file.")
    if len(pgn_text.encode()) > MAX_PGN_BYTES:
        raise InvalidPGNError("This PGN is too large (more than 5 MB). Please split it into smaller files.")
    if played_as not in PLAYED_AS_CHOICES:
        raise InvalidPGNError("Please choose which side you played.")

    names = _user_names(user)
    seen = game_repository.get_fingerprints(user)
    result = ImportResult()
    rows = []
    for number, game in _read_games(pgn_text):
        white, black = _header(game, "White"), _header(game, "Black")
        name = f"Game {number}" + (f" ({white or '?'} vs {black or '?'})" if white or black else "")
        if not list(game.mainline_moves()):
            result.errors.append(f"{name}: no moves found.")
            continue
        if game.errors:
            result.errors.append(f"{name}: contains an illegal or unreadable move.")
            continue

        # Store each game's own PGN, not the whole uploaded text.
        own_pgn = game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True))
        fingerprint = _fingerprint(game, own_pgn)
        if fingerprint in seen:
            result.duplicates += 1
            continue
        seen.add(fingerprint)

        rows.append({
            "pgn": own_pgn,
            "white": white,
            "black": black,
            "result": _header(game, "Result"),
            "played_on": _played_on(game),
            "opening": _opening(game),
            "fingerprint": fingerprint,
            "user_color": detect_user_color(user, white, black, names) if played_as == "auto" else played_as,
        })

    if not rows and not result.duplicates:
        raise InvalidPGNError(result.errors[0] if len(result.errors) == 1 else "No valid games found in this PGN.")
    result.games = game_repository.create_games(user, rows)
    return result
