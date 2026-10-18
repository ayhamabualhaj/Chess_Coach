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
    played_on = models.DateField(null=True, blank=True)  # the PGN's Date header
    opening = models.CharField(max_length=200, blank=True)
    # Identifies the game for duplicate checks: its Lichess/Chess.com link, or a hash of its PGN.
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
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

    @property
    def user_outcome(self) -> str:
        """The result from the uploading user's side: "win", "loss", "draw", or "" if unknown."""
        if self.result == "1/2-1/2":
            return "draw"
        if not self.user_color or self.result not in ("1-0", "0-1"):
            return ""
        white_won = self.result == "1-0"
        return "win" if white_won == (self.user_color == self.Side.WHITE) else "loss"
