from apps.games.models import Game


def create_game(user, pgn: str, white: str = "", black: str = "", result: str = "") -> Game:
    return Game.objects.create(user=user, pgn=pgn, white=white, black=black, result=result)


def list_games_for_user(user):
    return Game.objects.filter(user=user)