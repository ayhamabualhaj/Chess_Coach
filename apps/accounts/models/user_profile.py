from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    # Optional: the coach uses it to pitch advice at the right level.
    rating = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(100), MaxValueValidator(3500)],
    )
    lichess_username = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile of {self.user}"