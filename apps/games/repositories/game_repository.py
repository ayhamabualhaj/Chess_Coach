from django.db.models import Count, F, Q
from django.utils import timezone
from apps.games.models import Game, Move

IN_PROGRESS = (Game.Status.QUEUED, Game.Status.RUNNING)

# Filters for the games list: name -> condition.
GAME_FILTERS = {
    "all": Q(),
    "todo": ~Q(status=Game.Status.DONE),
    "done": Q(status=Game.Status.DONE),
    "side": Q(user_color=""),
}


def create_games(user, rows: list[dict]) -> list[Game]:
    """Save many games in one query. The first game of the file is saved last,
    so it is the newest and shows at the top of the list (PGN exports from
    Lichess and Chess.com put the most recent game first)."""
    games = Game.objects.bulk_create(Game(user=user, **row) for row in reversed(rows))
    return list(reversed(games))


def get_fingerprints(user) -> set[str]:
    return set(Game.objects.filter(user=user).exclude(fingerprint="").values_list("fingerprint", flat=True))


def list_games_for_user(user, show: str = "all"):
    return Game.objects.filter(user=user).filter(GAME_FILTERS.get(show, Q()))


def count_games_by_filter(user) -> dict:
    return Game.objects.filter(user=user).aggregate(
        **{name: Count("pk", filter=condition) for name, condition in GAME_FILTERS.items()}
    )


def count_in_progress(user) -> int:
    return Game.objects.filter(user=user, status__in=IN_PROGRESS).count()


def list_games_to_analyse(user, limit: int):
    """Games that have never been analysed successfully, oldest upload first."""
    return list(
        Game.objects.filter(user=user, status__in=[Game.Status.PENDING, Game.Status.FAILED])
        .order_by("created_at", "pk")[:limit]
    )


def count_games_to_analyse(user) -> int:
    return Game.objects.filter(user=user, status__in=[Game.Status.PENDING, Game.Status.FAILED]).count()


def delete_games(user, game_ids) -> int:
    """Delete the user's games with these ids; returns how many were deleted."""
    deleted, per_model = Game.objects.filter(user=user, pk__in=game_ids).delete()
    return per_model.get("games.Game", 0)


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
    game.status_changed_at = timezone.now()
    game.save(update_fields=["status", "analysis_error", "status_changed_at"])


def fail_stuck_games(older_than, message: str, user=None) -> int:
    """Mark games waiting or analysing since before `older_than` as failed; returns how many."""
    games = Game.objects.filter(status__in=IN_PROGRESS, status_changed_at__lt=older_than)
    if user is not None:
        games = games.filter(user=user)
    return games.update(status=Game.Status.FAILED, analysis_error=message[:200], status_changed_at=timezone.now())


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