"""Logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure root logging once, at application start-up."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
