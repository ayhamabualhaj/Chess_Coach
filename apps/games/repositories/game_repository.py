from apps.games.models import Game


def create_game(user, pgn: str, white: str = "", black: str = "", result: str = "") -> Game:
    return Game.objects.create(user=user, pgn=pgn, white=white, black=black, result=result)


def list_games_for_user(user):
    return Game.objects.filter(user=user)


def get_game(game_id: int) -> Game:
    return Game.objects.get(pk=game_id)


def get_game_for_user(user, game_id: int) -> Game | None:
    # Filtering by user means nobody can open someone else's game by guessing its id.
    return Game.objects.filter(user=user, pk=game_id).first()


def list_moves_with_mistakes(game: Game):
    # select_related fetches each move's mistake in the same query.
    return game.moves.select_related("mistake").order_by("ply")


def set_status(game: Game, status: str, error: str = "") -> None:
    game.status = status
    game.analysis_error = error[:200]
    game.save(update_fields=["status", "analysis_error"])
