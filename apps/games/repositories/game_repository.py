from apps.games.models import Game


def create_game(user, pgn: str) -> Game:
    return Game.objects.create(user=user, pgn=pgn)


def list_games_for_user(user):
    return Game.objects.filter(user=user)