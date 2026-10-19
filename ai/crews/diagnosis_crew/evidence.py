import re
from dataclasses import dataclass

from ai.tools.stats_tools import MoveRecord, best_move_san

SAN = r"(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)[+#]?"
NUMBERED_MOVE = re.compile(rf"(?<![\w.])(\d+)\s*(\.\.\.|…|\.)\s*({SAN})(?![\w=])")
PIECE_MOVE = re.compile(
    rf"(?<![\w.…])((?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8]=[QRBN])[+#]?)(?![\w=])"
)


def _plain(san: str) -> str:
    return san.rstrip("+#!?")


def _move_number(ply: int) -> tuple[int, str]:
    return (ply + 1) // 2, "white" if ply % 2 else "black"


@dataclass
class KnownMoves:
    played: set[tuple[int, str, str]]
    any_move: set[str]

    @classmethod
    def from_records(cls, records: list[MoveRecord]) -> "KnownMoves":
        played, any_move = set(), set()
        for record in records:
            number, color = _move_number(record.ply)
            played.add((number, color, _plain(record.san)))
            any_move.add(_plain(record.san))
            best = best_move_san(record.fen_before, record.best_move_uci)
            if best:
                any_move.add(_plain(best))
        return cls(played, any_move)

    def cited_moves(self, evidence: str) -> list[tuple[str, bool]]:
        cited = []
        numbered_spans = []
        for match in NUMBERED_MOVE.finditer(evidence):
            numbered_spans.append(match.span(3))
            number, dots, san = int(match.group(1)), match.group(2), match.group(3)
            color = "white" if dots == "." else "black"
            cited.append((match.group(0).strip(), (number, color, _plain(san)) in self.played))
        for match in PIECE_MOVE.finditer(evidence):
            if any(start <= match.start(1) < end for start, end in numbered_spans):
                continue
            cited.append((match.group(1), _plain(match.group(1)) in self.any_move))
        return cited

    def unknown_moves(self, evidence: str) -> list[str]:
        return list(dict.fromkeys(move for move, known in self.cited_moves(evidence) if not known))