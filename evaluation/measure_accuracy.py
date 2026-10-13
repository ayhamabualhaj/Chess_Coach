"""Accuracy of our mistake labels, compared with the labels Lichess wrote into its PGN export.

Pure Python, no Django. A game exported from Lichess "with computer analysis"
marks each judged move with a glyph: ?! (inaccuracy), ? (mistake), ?? (blunder),
plus a comment such as { Blunder. g6 was best. }. python-chess reads the glyphs
as NAGs (Numeric Annotation Glyphs, part of the PGN standard).

Each move is one prediction: "is this move an inaccuracy, mistake or blunder?"
Lichess's label is the reference (ground truth), ours is the prediction.
"""
import re

import chess.pgn

SEVERITIES = ("inaccuracy", "mistake", "blunder")

NAG_TO_SEVERITY = {
    chess.pgn.NAG_DUBIOUS_MOVE: "inaccuracy",  # ?!
    chess.pgn.NAG_MISTAKE: "mistake",  # ?
    chess.pgn.NAG_BLUNDER: "blunder",  # ??
}
COMMENT_LABEL = re.compile(r"\b(Inaccuracy|Mistake|Blunder)\b")


def has_lichess_analysis(game: chess.pgn.Game) -> bool:
    """True if the game carries Lichess's computer analysis: [%eval] comments or move glyphs."""
    return any(
        node.eval() is not None or any(nag in NAG_TO_SEVERITY for nag in node.nags)
        for node in game.mainline()
    )


def lichess_labels(game: chess.pgn.Game) -> dict[int, str]:
    """{ply: severity} for every move Lichess labelled (ply 1 = White's first move)."""
    labels = {}
    for node in game.mainline():
        severity = next((NAG_TO_SEVERITY[nag] for nag in node.nags if nag in NAG_TO_SEVERITY), None)
        if severity is None:
            # Fallback: some exports only have the word in the comment.
            match = COMMENT_LABEL.search(node.comment)
            severity = match.group(1).lower() if match else None
        if severity:
            labels[node.ply()] = severity
    return labels


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def scores(true_pos: int, false_pos: int, false_neg: int) -> dict:
    """Precision, recall and F1 from the three counts (None when undefined)."""
    precision = _ratio(true_pos, true_pos + false_pos)
    recall = _ratio(true_pos, true_pos + false_neg)
    f1 = (
        round(2 * precision * recall / (precision + recall), 3)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def compare(ours: dict[int, str], theirs: dict[int, str], plies: int) -> dict:
    """Compare our {ply: severity} with Lichess's for one game of `plies` moves.

    A true positive is a move both sides labelled (any severity); same_severity
    counts those where the severity is also the same. The confusion matrix is
    {lichess_label: {our_label: count}}, with "none" for unlabelled moves.
    """
    labelled_by_both = ours.keys() & theirs.keys()
    true_pos = len(labelled_by_both)
    false_pos = len(ours.keys() - theirs.keys())
    false_neg = len(theirs.keys() - ours.keys())

    kinds = ("none", *SEVERITIES)
    confusion = {lichess: {our: 0 for our in kinds} for lichess in kinds}
    for ply in range(1, plies + 1):
        confusion[theirs.get(ply, "none")][ours.get(ply, "none")] += 1

    return {
        "lichess_labels": len(theirs),
        "our_labels": len(ours),
        "true_pos": true_pos,
        "false_pos": false_pos,
        "false_neg": false_neg,
        "same_severity": sum(1 for ply in labelled_by_both if ours[ply] == theirs[ply]),
        "confusion": confusion,
        **scores(true_pos, false_pos, false_neg),
    }
