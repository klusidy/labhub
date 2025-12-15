import logging
import sys
import os

_ROOT_LOGGER_NAME = None

def _level_from_env(default=logging.INFO) -> int:
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


def init_logging(level: int | None = None):
    """Initialize logging. If level is None, check LABHUB_LOG_LEVEL env var else use INFO."""
    if level is None:
        level = _level_from_env(logging.INFO)

    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout,
    )
    # Silence overly verbose loggers if needed (but allow them to be controlled via set_level)
    logging.getLogger('uvicorn').setLevel(level)
    logging.getLogger('uvicorn.error').setLevel(level)
    logging.getLogger('uvicorn.access').setLevel(level)
    logging.getLogger('asyncio').setLevel(level)


def set_level(level_name: str) -> dict:
    """Set root logging level at runtime. Accepts level name like 'DEBUG' or numeric string.
    Returns a dict with previous and new levels.
    """
    root = logging.getLogger()
    prev = logging.getLevelName(root.level)
    try:
        level = getattr(logging, level_name.upper())
    except Exception:
        try:
            level = int(level_name)
        except Exception:
            raise ValueError(f"Invalid level: {level_name}")
    root.setLevel(level)
    return {"previous": prev, "new": logging.getLevelName(level)}


def get_level() -> str:
    root = logging.getLogger()
    return logging.getLevelName(root.level)
