"""Latency: how long one piece of work takes, measured with a monotonic clock."""
import time
from contextlib import contextmanager


@contextmanager
def stopwatch():
    """with stopwatch() as watch: ...   then watch["seconds"] holds the elapsed time.

    time.perf_counter is the clock Python recommends for measuring durations
    (https://docs.python.org/3/library/time.html#time.perf_counter).
    """
    watch = {"seconds": None}
    started = time.perf_counter()
    try:
        yield watch
    finally:
        watch["seconds"] = round(time.perf_counter() - started, 3)
