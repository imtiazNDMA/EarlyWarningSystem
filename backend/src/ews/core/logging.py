"""Logging configuration."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# The monitoring run the current task is working on, if any
_run_id: ContextVar[int | None] = ContextVar("run_id", default=None)


@contextmanager
def bound_run_id(run_id: int) -> Iterator[None]:
    """Mark every log line written inside the block as belonging to the run."""
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


class RunIdFilter(logging.Filter):
    """Adds ``run_id`` to each record: the bound run, or ``-`` outside one."""

    def filter(self, record: logging.LogRecord) -> bool:
        run_id = _run_id.get()
        record.run_id = "-" if run_id is None else run_id
        return True


def configure_logging(level: str) -> None:
    """Configure root logging once, at application start-up."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s run=%(run_id)s %(message)s",
    )
    # On the handlers, so records from every logger pass through it
    for handler in logging.getLogger().handlers:
        handler.addFilter(RunIdFilter())
