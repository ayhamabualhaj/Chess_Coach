"""Memory: the peak memory used by our Python code while it works.

tracemalloc (Python standard library) records every memory block Python
allocates, so its peak is the most memory our own code held at one time.
Stockfish runs as a separate program; its memory is measured separately by
StockfishEngine.peak_memory_mb() (ai/engine/stockfish_wrapper.py).
https://docs.python.org/3/library/tracemalloc.html
"""
import tracemalloc
from contextlib import contextmanager


@contextmanager
def python_memory():
    """with python_memory() as memory: ...   then memory["peak_mb"] holds the peak in MB."""
    memory = {"peak_mb": None}
    tracemalloc.start()
    try:
        yield memory
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory["peak_mb"] = round(peak / (1024 * 1024), 2)
