"""Errors raised by data-source clients."""


class SourceError(Exception):
    """A data source could not be read or returned something unusable."""

    def __init__(self, source: str, message: str) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source
