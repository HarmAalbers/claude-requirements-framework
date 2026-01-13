#!/usr/bin/env python3
"""
Console output utilities with configurable destinations and levels.

This module standardizes non-structured output (warnings, user-facing notices)
separately from JSON logging. It keeps hooks fail-open by swallowing output
errors and provides opt-in configuration for destinations and verbosity.
Defaults are silent unless explicitly enabled in config.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TextIO

try:
    from logger import LEVELS
except Exception:
    LEVELS = {
        "debug": 10,
        "info": 20,
        "warning": 30,
        "error": 40,
    }


DEFAULT_CONSOLE_CONFIG = {
    "level": "error",
    "destinations": [],
}
DEFAULT_CONSOLE_FILE = Path.home() / ".claude" / "requirements-console.log"


class OutputHandler:
    """Base handler for emitting plain-text output."""

    def emit(self, message: str) -> None:
        raise NotImplementedError


class StreamHandler(OutputHandler):
    """Handler that writes messages to a stream (stdout/stderr)."""

    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self.stream = stream or sys.stderr

    def emit(self, message: str) -> None:
        try:
            self.stream.write(_ensure_trailing_newline(message))
            self.stream.flush()
        except Exception:
            # Fail-open: never let console output break hooks
            pass


class FileHandler(OutputHandler):
    """Handler that appends messages to a file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def emit(self, message: str) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(_ensure_trailing_newline(message))
        except Exception:
            # Fail-open: never let console output break hooks
            pass


@dataclass(frozen=True)
class Console:
    """Simple, level-aware console output."""

    level_name: str
    level: int
    handlers: tuple[OutputHandler, ...]

    def debug(self, message: str, *, force: bool = False) -> None:
        self._log("debug", message, force=force)

    def info(self, message: str, *, force: bool = False) -> None:
        self._log("info", message, force=force)

    def warning(self, message: str, *, force: bool = False) -> None:
        self._log("warning", message, force=force)

    def error(self, message: str, *, force: bool = False) -> None:
        self._log("error", message, force=force)

    def _log(self, level: str, message: str, *, force: bool = False) -> None:
        if not force and LEVELS.get(level, 0) < self.level:
            return
        if not self.handlers:
            return

        text = message if isinstance(message, str) else str(message)
        for handler in self.handlers:
            try:
                handler.emit(text)
            except Exception:
                pass


_console: Optional[Console] = None


def _ensure_trailing_newline(message: str) -> str:
    if message.endswith("\n"):
        return message
    return f"{message}\n"


def _build_handlers(console_config: dict) -> list[OutputHandler]:
    destinations = console_config.get("destinations", DEFAULT_CONSOLE_CONFIG["destinations"])
    if isinstance(destinations, str):
        destinations = [destinations]
    if destinations is None:
        destinations = []

    handlers: list[OutputHandler] = []

    for destination in destinations:
        dest = (destination or "").lower().strip()
        if dest == "stdout":
            handlers.append(StreamHandler(stream=sys.stdout))
        elif dest == "stderr":
            handlers.append(StreamHandler(stream=sys.stderr))
        elif dest == "file":
            file_path = console_config.get("file", DEFAULT_CONSOLE_FILE)
            try:
                handlers.append(FileHandler(Path(file_path)))
            except Exception:
                continue

    return handlers


def _build_console(config: Optional[dict]) -> Console:
    merged = dict(DEFAULT_CONSOLE_CONFIG)
    if isinstance(config, dict):
        merged.update(config)

    level_name = str(merged.get("level", DEFAULT_CONSOLE_CONFIG["level"])).lower()
    level = LEVELS.get(level_name, LEVELS[DEFAULT_CONSOLE_CONFIG["level"]])
    handlers = _build_handlers(merged)
    return Console(level_name=level_name, level=level, handlers=tuple(handlers))


def get_console() -> Console:
    """Get the configured console (lazy initialized)."""
    global _console
    if _console is None:
        _console = _build_console(None)
    return _console


def configure_console(config: Optional[dict]) -> Console:
    """Configure the shared console instance from config."""
    global _console
    _console = _build_console(config)
    return _console


def emit_text(message: str, stream: Optional[TextIO] = None) -> None:
    """Write text to a stream (stdout by default)."""
    target = stream or sys.stdout
    try:
        target.write(_ensure_trailing_newline(message))
        target.flush()
    except Exception:
        pass


def emit_json(payload: dict, stream: Optional[TextIO] = None) -> None:
    """Write JSON payload to a stream (stdout by default)."""
    emit_text(json.dumps(payload), stream=stream)
