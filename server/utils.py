import logging
import sys
import os
from pathlib import Path

# Root logger for all LabHub components
ROOT_LOGGER = "labhub"


class ColoredFormatter(logging.Formatter):
    """Formatter with colored level names matching Uvicorn style."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[1;31m",  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record):
        # Color the level name
        levelname = record.levelname
        if levelname in self.COLORS:
            colored_levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}:"
        else:
            colored_levelname = f"{levelname}:"

        # Format: LEVEL:     logger_name: message
        # Pad to align logger names (longest level is "CRITICAL:" = 9 chars + padding)
        return f"{colored_levelname:<18} {record.name}: {record.getMessage()}"


def _level_from_env(default=logging.INFO) -> int:
    """Get logging level from LABHUB_LOG_LEVEL environment variable."""
    val = os.environ.get("LABHUB_LOG_LEVEL")
    if not val:
        return default
    try:
        return getattr(logging, val.upper())
    except Exception:
        try:
            return int(val)
        except Exception:
            return default


def init_logging(level: int | None = None, log_file: str | Path | None = None):
    """
    Initialize LabHub logging.

    Args:
        level: Logging level (int or None). If None, checks LABHUB_LOG_LEVEL env var.
        log_file: Optional file path to also log to file (in addition to console).

    Environment Variables:
        LABHUB_LOG_LEVEL: Set default level (e.g., "DEBUG", "INFO", "WARNING")

    Examples:
        init_logging()                           # INFO to console
        init_logging(logging.DEBUG)              # DEBUG to console
        init_logging(log_file="labhub.log")      # INFO to console + file
    """
    if level is None:
        level = _level_from_env(logging.INFO)

    # Get root logger and set level
    root_logger = logging.getLogger(ROOT_LOGGER)
    root_logger.setLevel(level)

    # Console handler (stdout) with colored formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(console_handler)

    # Optional file handler (without colors)
    if log_file:
        # Plain formatter for file output (no ANSI colors)
        file_formatter = logging.Formatter(
            fmt="%(levelname)s:          %(name)s: %(message)s"
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Control noisy third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    root_logger.info(
        f"LabHub logging initialized at level {logging.getLevelName(level)}"
    )


def set_level(level_name: str, logger_name: str | None = None) -> dict:
    """
    Set logging level at runtime.

    Args:
        level_name: Level name ('DEBUG', 'INFO', etc.) or numeric string
        logger_name: Specific logger to set (None = root 'labhub' logger)

    Returns:
        Dict with 'previous' and 'new' level names

    Examples:
        set_level("DEBUG")                              # Set root labhub logger
        set_level("WARNING", "labhub.drivers")          # Set all drivers
        set_level("DEBUG", "labhub.drivers.kinesis")    # Set one driver family
    """
    target_logger = logging.getLogger(logger_name or ROOT_LOGGER)
    prev = logging.getLevelName(target_logger.level)

    try:
        level = getattr(logging, level_name.upper())
    except AttributeError:
        try:
            level = int(level_name)
        except ValueError:
            raise ValueError(f"Invalid level: {level_name}")

    target_logger.setLevel(level)
    logger_path = logger_name or ROOT_LOGGER

    return {"logger": logger_path, "previous": prev, "new": logging.getLevelName(level)}


def get_level(logger_name: str | None = None) -> str:
    """
    Get current logging level.

    Args:
        logger_name: Specific logger to query (None = root 'labhub' logger)

    Returns:
        Level name as string (e.g., "INFO", "DEBUG")
    """
    target_logger = logging.getLogger(logger_name or ROOT_LOGGER)
    return logging.getLevelName(target_logger.level)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger under the labhub namespace.

    Args:
        name: Module name (use __name__ from your module)

    Returns:
        Logger instance

    Usage:
        # In your module:
        from .utils import get_logger
        logger = get_logger(__name__)
        logger.info("Hello")
    """
    return logging.getLogger(name)
