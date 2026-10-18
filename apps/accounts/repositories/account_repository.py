from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile


def create_user(username: str, password: str):
    # create_user hashes the password; it is never stored as plain text.
    return get_user_model().objects.create_user(username=username, password=password)


def create_profile(user, rating=None, lichess_username: str = "") -> UserProfile:
    return UserProfile.objects.create(
        user=user, rating=rating, lichess_username=lichess_username
    )


def get_profile(user) -> UserProfile | None:
    return UserProfile.objects.filter(user=user).first()


def lock_user(user) -> None:
    # Inside transaction.atomic(): a second request from the same user waits here until
    # the first one has finished, so "check, then create" cannot run twice at once.
    get_user_model().objects.select_for_update().get(pk=user.pk)