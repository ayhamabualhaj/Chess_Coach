from django.db import models


class TrainingPlan(models.Model):
    """The practice list for one report: Lichess puzzle sets chosen from the
    player's own mistake types (built by ai/tools/practice_tools.py)."""

    report = models.OneToOneField(
        "coaching.WeaknessReport",
        on_delete=models.CASCADE,
        related_name="training_plan",
    )
    # List of dicts: theme, name, url, puzzles, mistakes, blunders, examples, done.
    tasks = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Practice plan for {self.report.user}"

    @property
    def done_count(self) -> int:
        return sum(1 for task in self.tasks if task.get("done"))

    @property
    def total_puzzles(self) -> int:
        return sum(task.get("puzzles", 0) for task in self.tasks)