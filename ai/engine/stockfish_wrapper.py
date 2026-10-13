"""Thin wrapper around the Stockfish chess engine.

Pure Python: no Django imports, so it can be used and tested on its own.
"""
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine

# Centipawn value used for "forced mate", so mates fit in an integer field.
MATE_SCORE = 10_000


class EngineNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class PositionEval:
    cp: int  # centipawns from White's point of view; mates become +/- MATE_SCORE
    mate: int | None  # moves until mate (+ White mates, - Black mates), None if no forced mate
    best_move: chess.Move | None  # None when the game is already over
    depth: int


class StockfishEngine:
    """Use as a context manager so the engine process is always closed:

        with StockfishEngine("/usr/bin/stockfish") as engine:
            result = engine.evaluate(chess.Board())
    """

    def __init__(self, path: str, depth: int = 12, threads: int = 1, hash_mb: int = 64):
        self.path = path
        self.depth = depth
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine = None

    def open(self):
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        except FileNotFoundError as e:
            raise EngineNotFoundError(f"Stockfish not found at {self.path!r}") from e
        # One thread keeps fixed-depth results reproducible between runs.
        self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        return self

    def close(self):
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def peak_memory_mb(self) -> float | None:
        """The most memory (RAM) the Stockfish process has used so far, in MB.

        Read from Linux's /proc/<pid>/status ("VmHWM" = peak resident memory);
        None on other systems or when the engine is not running.
        """
        if self._engine is None:
            return None
        try:
            status = Path(f"/proc/{self._engine.transport.get_pid()}/status").read_text()
        except OSError:
            return None
        for line in status.splitlines():
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)  # the value is in kB
        return None

    def evaluate(self, board: chess.Board) -> PositionEval:
        return self._analyse(board)

    def evaluate_without(self, board: chess.Board, excluded: chess.Move) -> PositionEval | None:
        """The evaluation if `excluded` were not allowed: the best of all other moves.
        Used to see whether the best move was the only good one. None if there is no other move."""
        others = [move for move in board.legal_moves if move != excluded]
        if not others:
            return None
        return self._analyse(board, root_moves=others)

    def _analyse(self, board: chess.Board, root_moves=None) -> PositionEval:
        if self._engine is None:
            raise RuntimeError("Engine is not open; use 'with StockfishEngine(...)'.")

        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth), root_moves=root_moves)
        score = info["score"].white()
        pv = info.get("pv") or []
        return PositionEval(
            cp=score.score(mate_score=MATE_SCORE),
            mate=score.mate(),
            best_move=pv[0] if pv else None,
            depth=info.get("depth", 0),
        )