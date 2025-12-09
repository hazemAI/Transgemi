"""In-memory logging handler that flushes to disk on demand."""

from __future__ import annotations

import atexit
import logging
from pathlib import Path
from typing import List, Optional


class MemoryLogHandler(logging.Handler):
    """Collect log records in memory until explicitly flushed."""

    def __init__(self, level: int = logging.INFO, formatter: Optional[logging.Formatter] = None) -> None:
        super().__init__(level)
        if formatter is None:
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s: %(message)s")
        self.setFormatter(formatter)
        self._records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - relies on logging framework
        try:
            message = self.format(record)
        except Exception:  # pylint: disable=broad-except
            message = record.getMessage()
        self.acquire()
        try:
            self._records.append(message)
        finally:
            self.release()

    def write_to_file(self, path: Path) -> None:
        if not self._records:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(self._records))
            handle.write("\n")
        self.clear()

    def clear(self) -> None:
        self.acquire()
        try:
            self._records.clear()
        finally:
            self.release()


_memory_handler: Optional[MemoryLogHandler] = None
_log_path: Optional[Path] = None


def prune_translator_log(log_path: Path, max_sessions: int = 3) -> None:
    """Prune log file to keep only the last N sessions."""
    if not log_path.exists():
        return

    try:
        data = log_path.read_text(encoding="utf-8")
    except Exception:
        return

    lines = data.splitlines()
    session_starts = [i for i, line in enumerate(lines)
                      if "Application started successfully" in line]

    if len(session_starts) < max_sessions:
        return

    keep_idx = session_starts[-max_sessions]
    trimmed_lines = lines[keep_idx:]
    new_content = "\n".join(trimmed_lines)
    if trimmed_lines:
        new_content += "\n"

    try:
        log_path.write_text(new_content, encoding="utf-8")
    except Exception:
        pass


def init_memory_logging(log_path: Path, level: int = logging.INFO) -> MemoryLogHandler:
    """Create (or return existing) memory handler and record target log file."""
    global _memory_handler, _log_path
    if _memory_handler is None:
        _memory_handler = MemoryLogHandler(level=level)
        atexit.register(flush_logs)
    _log_path = log_path
    return _memory_handler


def flush_logs() -> None:
    """Flush buffered log lines to disk if possible."""
    if _memory_handler is None or _log_path is None:
        return
    _memory_handler.write_to_file(_log_path)


def memory_handler() -> Optional[MemoryLogHandler]:
    """Expose the current memory handler (useful for testing)."""
    return _memory_handler
