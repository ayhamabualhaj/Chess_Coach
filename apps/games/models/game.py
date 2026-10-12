# apps/games/models/game.py
from django.conf import settings
from django.db import models


class Game(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Not analysed yet"
        QUEUED = "queued", "Waiting for analysis"
        RUNNING = "running", "Analysing"
        DONE = "done", "Analysed"
        FAILED = "failed", "Analysis failed"

    class Side(models.TextChoices):
        WHITE = "white", "White"
        BLACK = "black", "Black"

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
    # Which side the uploading user played; coaching only looks at their own moves.
    user_color = models.CharField(max_length=5, choices=Side.choices, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Short reason shown to the user when the analysis fails.
    analysis_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.white or self.black:
            return f"{self.white or '?'} vs {self.black or '?'}"
        return f"Game {self.pk} by {self.user}"