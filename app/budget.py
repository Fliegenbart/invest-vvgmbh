"""Cooperative wall-clock budget; host termination remains the final limit."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
_deadline = ContextVar('pia_deadline', default=None)
@contextmanager
def time_budget(seconds):
    token = _deadline.set(time.monotonic() + seconds if seconds else None)
    try: yield
    finally: _deadline.reset(token)
def timeout(default):
    deadline = _deadline.get()
    if deadline is None: return default
    remaining = deadline - time.monotonic()
    if remaining < 1:
        from .network import ResearchError
        raise ResearchError('Zeitbudget erreicht. Kein unvollständiger Bericht wird als abgeschlossen ausgegeben.')
    return min(default, remaining)
