from django.db import models


class TrainingPlan(models.Model):
    """The coach's plan for fixing the weaknesses in one report.

    Written by the same agent run as the report, so the AI cost and timing
    are stored on the WeaknessReport.
    """

    report = models.OneToOneField(
        "coaching.WeaknessReport",
        on_delete=models.CASCADE,
        related_name="training_plan",
    )
    # How long the plan is meant to take.
    days = models.PositiveSmallIntegerField(default=7)
    overview = models.TextField()
    # List of dicts: day, focus, activity, minutes.
    tasks = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.days}-day plan for {self.report.user}"