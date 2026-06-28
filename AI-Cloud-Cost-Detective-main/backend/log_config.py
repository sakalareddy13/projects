"""Centralized logging configuration for the backend."""

import logging
import os
import sys


def configure_logging() -> None:
    """
    Configure root logger.
    - LOG_FORMAT=json  → structured JSON (Datadog / CloudWatch / Loki ready)
    - LOG_FORMAT=text  → human-readable colored output (default for local dev)
    LOG_LEVEL controls verbosity (default: info).
    """
    level_name = os.getenv("LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.getenv("LOG_FORMAT", "text").lower()

    if fmt == "json":
        try:
            from pythonjsonlogger import jsonlogger  # type: ignore
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s",
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            ))
        except ImportError:
            handler = _text_handler()
    else:
        handler = _text_handler()

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers at WARNING unless debug mode
    for noisy in ("boto3", "botocore", "urllib3", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING if level < logging.DEBUG else level)


def _text_handler() -> logging.StreamHandler:
    GREY   = "\033[38;5;244m"
    YELLOW = "\033[33m"
    RED    = "\033[31m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG:    GREY,
            logging.INFO:     RESET,
            logging.WARNING:  YELLOW,
            logging.ERROR:    RED,
            logging.CRITICAL: BOLD + RED,
        }

        def format(self, record: logging.LogRecord) -> str:
            color = self.COLORS.get(record.levelno, RESET)
            name = f"{GREY}{record.name}{RESET}"
            lvl  = f"{color}{record.levelname:<8}{RESET}"
            msg  = super().format(record)
            # Strip the default prefix so we can rebuild it
            bare = record.getMessage()
            if record.exc_info:
                bare = self.formatException(record.exc_info)
            return f"{lvl} {name}  {bare}"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())
    return handler
