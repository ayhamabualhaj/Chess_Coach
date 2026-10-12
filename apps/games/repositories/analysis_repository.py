from django.db import transaction

from apps.games.models import Mistake, Move


@transaction.atomic
def replace_analysis(game, move_rows: list[dict], mistake_rows: list[dict]) -> None:
    """Delete any old analysis of the game and save the new one in one transaction.

    move_rows: field values for each Move (without "game").
    mistake_rows: field values for each Mistake, with "ply" saying which move it belongs to.
    """
    Move.objects.filter(game=game).delete()  # also deletes old mistakes (CASCADE)
    moves = Move.objects.bulk_create(Move(game=game, **row) for row in move_rows)

    move_by_ply = {move.ply: move for move in moves}
    Mistake.objects.bulk_create(
        Mistake(
            move=move_by_ply[row["ply"]],
            severity=row["severity"],
            phase=row["phase"],
            motif=row.get("motif", ""),
        )
        for row in mistake_rows
    )