import io

import chess.pgn

from apps.games.repositories import game_repository


class InvalidPGNError(Exception):
    pass


def _header(game, name: str) -> str:
    # PGN uses "?" for unknown values; store those as empty.
    value = game.headers.get(name, "")
    return "" if value in ("?", "*") else value


def import_pgn(user, pgn_text: str):
    pgn_text = pgn_text.strip()
    if not pgn_text:
        raise InvalidPGNError("Please paste a PGN.")

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None or not list(game.mainline_moves()):
        raise InvalidPGNError("No moves found in this PGN.")
    if game.errors:
        raise InvalidPGNError("This PGN contains an illegal or unreadable move.")

    return game_repository.create_game(
        user,
        pgn_text,
        white=_header(game, "White"),
        black=_header(game, "Black"),
        result=_header(game, "Result"),
    )