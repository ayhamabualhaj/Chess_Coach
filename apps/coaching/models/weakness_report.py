from django.conf import settings
from django.db import models


class WeaknessReport(models.Model):
    """One run of the diagnosis agent over a player's analysed games."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Waiting"
        RUNNING = "running", "Working"
        DONE = "done", "Ready"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weakness_reports",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    # Short reason shown to the user when the agent fails.
    error = models.CharField(max_length=200, blank=True)

    # What the report is based on.
    games_count = models.PositiveIntegerField(default=0)
    moves_count = models.PositiveIntegerField(default=0)

    # The agent's answer (DiagnosisResult.summary / .weaknesses).
    summary = models.TextField(blank=True)
    # List of dicts: title, category, explanation, evidence, example_game_ids, priority.
    weaknesses = models.JSONField(default=list, blank=True)

    # How the agent got there, for the performance report.
    ai_model = models.CharField(max_length=50, blank=True)
    turns = models.PositiveSmallIntegerField(default=0)
    # List of dicts: name, seconds, is_error.
    tool_calls = models.JSONField(default=list, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    seconds = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Weakness report {self.pk} for {self.user}"