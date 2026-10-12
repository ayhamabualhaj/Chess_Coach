# apps/games/models/game.py
from django.conf import settings
from django.db import models


class Game(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Not analysed yet"
        RUNNING = "running", "Analysing"
        DONE = "done", "Analysed"
        FAILED = "failed", "Analysis failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="games",
    )
    pgn = models.TextField()
    # Copied from the PGN headers so lists don't have to re-parse every game.
    white = models.CharField(max_length=100, blank=True)
    black = models.CharField(max_length=100, blank=True)
    result = models.CharField(max_length=10, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.white or self.black:
            return f"{self.white or '?'} vs {self.black or '?'}"
        return f"Game {self.pk} by {self.user}"