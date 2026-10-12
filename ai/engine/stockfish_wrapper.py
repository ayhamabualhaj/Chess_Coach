"""Thin wrapper around the Stockfish chess engine.

Pure Python: no Django imports, so it can be used and tested on its own.
"""
from dataclasses import dataclass

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

    def evaluate(self, board: chess.Board) -> PositionEval:
        if self._engine is None:
            raise RuntimeError("Engine is not open; use 'with StockfishEngine(...)'.")

        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))
        score = info["score"].white()
        pv = info.get("pv") or []
        return PositionEval(
            cp=score.score(mate_score=MATE_SCORE),
            mate=score.mate(),
            best_move=pv[0] if pv else None,
            depth=info.get("depth", 0),
        )