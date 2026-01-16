import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
}


class Handler:
    """Base handler for emitting log records."""

    def emit(self, record: dict) -> None:
        raise NotImplementedError


class StdoutHandler(Handler):
    """Handler that writes JSON log records to stdout."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def emit(self, record: dict) -> None:
        try:
            self.stream.write(json.dumps(record) + "\n")
            self.stream.flush()
        except Exception as e:
            # Fail-open: never let logging break the hook
            # But try to notify user that logging is failing
            try:
                import sys
                sys.stderr.write(f"[LOGGING ERROR] Failed to write log: {e}\n")
                sys.stderr.flush()
            except Exception:
                # Truly fail-open as last resort
                pass


class FileHandler(Handler):
    """Handler that appends JSON log records to a file."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def emit(self, record: dict) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            # Fail-open: never let logging break the hook
            # But try to notify user that logging is failing
            try:
                import sys
                sys.stderr.write(f"[LOGGING ERROR] Failed to write log to {self.path}: {e}\n")
                sys.stderr.flush()
            except Exception:
                # Truly fail-open as last resort
                pass


class JsonLogger:
    """Lightweight JSON logger with pluggable handlers."""

    def __init__(
        self,
        level: str = "error",
        handlers: Optional[Iterable[Handler]] = None,
        context: Optional[dict] = None,
    ) -> None:
        self.level_name = level.lower()
        self.level = LEVELS.get(self.level_name, LEVELS["error"])
        self.handlers = list(handlers) if handlers else []
        self.context = context or {}

    def bind(self, **context: object) -> "JsonLogger":
        """Return a new logger with additional context fields."""
        merged = self.context.copy()
        for key, value in context.items():
            if value is not None:
                merged[key] = value
        return JsonLogger(self.level_name, self.handlers, merged)

    def debug(self, message: str, **fields: object) -> None:
        self._log("debug", message, fields)

    def info(self, message: str, **fields: object) -> None:
        self._log("info", message, fields)

    def warning(self, message: str, **fields: object) -> None:
        self._log("warning", message, fields)

    def error(self, message: str, **fields: object) -> None:
        self._log("error", message, fields)

    def _log(self, level: str, message: str, fields: dict) -> None:
        if LEVELS.get(level, 0) < self.level:
            return

        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
        }

        record.update(self.context)
        record.update({k: v for k, v in fields.items() if v is not None})

        for handler in self.handlers:
            try:
                handler.emit(record)
            except Exception:
                # Fail-open: never let logging break the hook
                pass


_LOGGER_STATE: dict[str, object] = {
    "level_name": None,
    "level": None,
    "handlers": None,
    "context": {},
}


def _merge_context(base_context: Optional[dict], extra_context: Optional[dict]) -> dict:
    merged = dict(base_context or {})
    if extra_context:
        for key, value in extra_context.items():
            if value is not None:
                merged[key] = value
    return merged


def _build_handlers(logging_config: dict) -> list[Handler]:
    destinations = logging_config.get("destinations", ["file"])
    if isinstance(destinations, str):
        destinations = [destinations]

    handlers: list[Handler] = []

    for destination in destinations:
        dest = (destination or "").lower()
        if dest == "stdout":
            handlers.append(StdoutHandler())
        elif dest == "file":
            file_path = logging_config.get(
                "file",
                Path.home() / ".claude" / "requirements.log",
            )
            try:
                handlers.append(FileHandler(Path(file_path)))
            except Exception:
                continue

    return handlers


def configure_logger(
    logging_config: Optional[dict] = None,
    base_context: Optional[dict] = None,
) -> JsonLogger:
    """
    Configure and return a shared JsonLogger instance.

    Args:
        logging_config: Config dict with optional keys: level, destinations, file
        base_context: Default context fields to include in every record

    Returns:
        JsonLogger instance with configured handlers
    """
    cfg = logging_config or {}
    level_name = str(cfg.get("level", "error")).lower()
    handlers = _build_handlers(cfg)
    context = _merge_context({}, base_context)

    _LOGGER_STATE["level_name"] = level_name
    _LOGGER_STATE["level"] = LEVELS.get(level_name, LEVELS["error"])
    _LOGGER_STATE["handlers"] = handlers
    _LOGGER_STATE["context"] = context

    return JsonLogger(level=level_name, handlers=handlers, context=context)


def get_logger(logging_config: Optional[dict] = None, base_context: Optional[dict] = None) -> JsonLogger:
    """
    Create a configured JsonLogger instance.

    Args:
        logging_config: Config dict with optional keys: level, destinations, file
        base_context: Default context fields to include in every record

    Returns:
        JsonLogger instance with configured handlers
    """
    if logging_config is not None:
        return configure_logger(logging_config, base_context)

    handlers = _LOGGER_STATE.get("handlers")
    level_name = _LOGGER_STATE.get("level_name")
    if handlers and level_name:
        context = _merge_context(_LOGGER_STATE.get("context"), base_context)
        return JsonLogger(level=level_name, handlers=handlers, context=context)

    return configure_logger({}, base_context)
