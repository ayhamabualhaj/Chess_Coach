from apps.games.repositories import game_repository


def list_games(user):
    return game_repository.list_games_for_user(user)