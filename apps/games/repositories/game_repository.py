from django.db.models import F

from apps.games.models import Game, Move


def create_game(user, pgn: str, white: str = "", black: str = "", result: str = "",
                user_color: str = "") -> Game:
    return Game.objects.create(
        user=user, pgn=pgn, white=white, black=black, result=result, user_color=user_color
    )


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


def set_user_color(game: Game, color: str) -> None:
    game.user_color = color
    game.save(update_fields=["user_color"])


def list_games_for_coaching(user):
    """Analysed games where we know which side the user played."""
    return Game.objects.filter(user=user, status=Game.Status.DONE).exclude(user_color="")

def get_ready_games(user, game_ids):
    """The subset of game_ids that belong to the user and are ready for coaching."""
    return list_games_for_coaching(user).filter(pk__in=game_ids)


def delete_game(game: Game) -> None:
    # Deletes its moves and mistakes too (on_delete=CASCADE).
    game.delete()



def list_user_moves(games):
    """The user's own moves in these games (not the opponent's), in game order."""
    return (
        Move.objects.filter(game__in=games, color=F("game__user_color"))
        .select_related("mistake")
        .order_by("game_id", "ply")
    )


def get_games_for_user(user, game_ids):
    return Game.objects.filter(user=user, pk__in=game_ids)


def count_games_by_state(user) -> dict:
    """How many of the user's games are ready for coaching, and why the others are not."""
    games = Game.objects.filter(user=user)
    analysed = games.filter(status=Game.Status.DONE)
    return {
        "ready": analysed.exclude(user_color="").count(),
        "missing_side": analysed.filter(user_color="").count(),
        "not_analysed": games.exclude(status=Game.Status.DONE).count(),
    }