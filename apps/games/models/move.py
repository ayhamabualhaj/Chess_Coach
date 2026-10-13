from django.db import models


class Move(models.Model):
    class Color(models.TextChoices):
        WHITE = "white", "White"
        BLACK = "black", "Black"

    class Label(models.TextChoices):
        """Chess.com-style move types, best first (see ai/engine/move_types.py)."""

        BRILLIANT = "brilliant", "Brilliant"
        GREAT = "great", "Great"
        BEST = "best", "Best"
        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        MISS = "miss", "Miss"
        INACCURACY = "inaccuracy", "Inaccuracy"
        MISTAKE = "mistake", "Mistake"
        BLUNDER = "blunder", "Blunder"

    game = models.ForeignKey(
        "games.Game",
        on_delete=models.CASCADE,
        related_name="moves",
    )
    # Half-move number: 1 = White's first move, 2 = Black's first move, ...
    ply = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=5, choices=Color.choices)
    san = models.CharField(max_length=10)  # e.g. "Nf3", "exd5", "O-O"
    uci = models.CharField(max_length=5)  # e.g. "g1f3", "e7e8q"
    fen_before = models.CharField(max_length=100)

    # Engine results, filled in by the analysis service.
    # Centipawns from White's point of view (+100 = White is a pawn up).
    eval_before = models.IntegerField(null=True, blank=True)
    eval_after = models.IntegerField(null=True, blank=True)
    best_move_uci = models.CharField(max_length=5, blank=True)
    # How much worse the played move was than the best move, for the mover.
    cp_loss = models.PositiveIntegerField(null=True, blank=True)
    # Move type shown on the game page; empty for games analysed before it existed.
    label = models.CharField(max_length=10, choices=Label.choices, blank=True)

    class Meta:
        ordering = ["game", "ply"]
        constraints = [
            models.UniqueConstraint(fields=["game", "ply"], name="unique_move_per_ply"),
        ]

    def __str__(self):
        number = (self.ply + 1) // 2
        dots = "." if self.color == self.Color.WHITE else "..."
        return f"{number}{dots} {self.san}"