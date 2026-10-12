import io

import chess.pgn

from apps.accounts.repositories import account_repository
from apps.games.repositories import game_repository

PLAYED_AS_CHOICES = ("auto", "white", "black")


class InvalidPGNError(Exception):
    pass


def _header(game, name: str) -> str:
    # PGN uses "?" for unknown values; store those as empty.
    value = game.headers.get(name, "")
    return "" if value in ("?", "*") else value


def detect_user_color(user, white: str, black: str) -> str:
    """Match the PGN player names against the user's username and Lichess name."""
    profile = account_repository.get_profile(user)
    names = {user.username.lower()}
    if profile and profile.lichess_username:
        names.add(profile.lichess_username.lower())
    if white.lower() in names:
        return "white"
    if black.lower() in names:
        return "black"
    return ""


def import_pgn(user, pgn_text: str, played_as: str = "auto"):
    pgn_text = pgn_text.strip()
    if not pgn_text:
        raise InvalidPGNError("Please paste a PGN.")

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None or not list(game.mainline_moves()):
        raise InvalidPGNError("No moves found in this PGN.")
    if game.errors:
        raise InvalidPGNError("This PGN contains an illegal or unreadable move.")

    if played_as not in PLAYED_AS_CHOICES:
        raise InvalidPGNError("Please choose which side you played.")

    white, black = _header(game, "White"), _header(game, "Black")
    user_color = detect_user_color(user, white, black) if played_as == "auto" else played_as

    return game_repository.create_game(
        user,
        pgn_text,
        white=white,
        black=black,
        result=_header(game, "Result"),
        user_color=user_color,
    )