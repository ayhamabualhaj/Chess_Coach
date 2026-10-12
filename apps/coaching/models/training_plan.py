from django.db import models


class TrainingPlan(models.Model):
    """The coach agent's plan, built from one weakness report."""

    report = models.OneToOneField(
        "coaching.WeaknessReport",
        on_delete=models.CASCADE,
        related_name="training_plan",
    )
    # How long the plan is meant to take.
    days = models.PositiveSmallIntegerField(default=7)
    overview = models.TextField()
    # List of dicts, one per training task, filled in by the coach agent (Step 17).
    tasks = models.JSONField(default=list, blank=True)

    # For the performance report, like on WeaknessReport.
    ai_model = models.CharField(max_length=50, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    seconds = models.FloatField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.days}-day plan for {self.report.user}"