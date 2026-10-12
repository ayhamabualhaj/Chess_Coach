from django.db import transaction

from apps.accounts.repositories import account_repository


@transaction.atomic
def register_user(username: str, password: str, rating=None, lichess_username: str = ""):
    # Atomic: if creating the profile fails, the user is rolled back too.
    user = account_repository.create_user(username, password)
    account_repository.create_profile(user, rating, lichess_username)
    return user