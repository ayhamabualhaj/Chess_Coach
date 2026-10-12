from django.db import models


class Mistake(models.Model):
    class Severity(models.TextChoices):
        INACCURACY = "inaccuracy", "Inaccuracy"
        MISTAKE = "mistake", "Mistake"
        BLUNDER = "blunder", "Blunder"

    class Phase(models.TextChoices):
        OPENING = "opening", "Opening"
        MIDDLEGAME = "middlegame", "Middlegame"
        ENDGAME = "endgame", "Endgame"

    move = models.OneToOneField(
        "games.Move",
        on_delete=models.CASCADE,
        related_name="mistake",
    )
    severity = models.CharField(max_length=10, choices=Severity.choices)
    phase = models.CharField(max_length=10, choices=Phase.choices)
    # Short tag added later by the AI tools, e.g. "hanging_piece".
    motif = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["move__game", "move__ply"]

    def __str__(self):
        return f"{self.get_severity_display()} at {self.move}"