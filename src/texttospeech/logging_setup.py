"""Журнал приложения: только файл, один перезаписываемый файл до 10 МБ.

Сторонние библиотеки (``silero_tts``, FFmpeg внутри ``QMediaPlayer``)
пишут в stderr. При запуске GUI мы направляем stderr в файл и убираем
консольный вывод, поэтому окно терминала остаётся чистым.
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import threading
from pathlib import Path

from .paths import LOG_PATH

MAX_LOG_BYTES = 10 * 1024 * 1024

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)


class CappedFile(io.TextIOBase):
    """Текстовый поток, который перезаписывает файл при достижении лимита."""

    def __init__(self, path: Path, limit: int = MAX_LOG_BYTES) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w+", encoding="utf-8")
        self._limit = limit
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        with self._lock:
            data = text.encode("utf-8")
            self._file.flush()
            size = os.path.getsize(self._file.name)
            if size + len(data) > self._limit:
                # Один файл без архивов: достигли лимита — пишем с начала.
                self._file.seek(0)
                self._file.truncate(0)
            written = self._file.write(text)
            self._file.flush()
            return written

    def flush(self) -> None:
        self._file.flush()

    def fileno(self) -> int:
        return self._file.fileno()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    @property
    def closed(self) -> bool:
        return self._file.closed

    def close(self) -> None:
        super().close()  # TextIOBase сам вызовет flush(), пока файл открыт
        self._file.close()


def setup_log_file(path: Path = LOG_PATH, limit: int = MAX_LOG_BYTES) -> CappedFile:
    """Создаёт перезаписываемый файл журнала (для тестов и настройки GUI)."""
    return CappedFile(path, limit)


_sink_id: int | None = None
_log_stream: CappedFile | None = None
_loguru_ready = False


def configure_logging(path: Path = LOG_PATH) -> Path:
    """Отправляет все логи в файл и убирает вывод в консоль.

    Повторный вызов при смене папки в настройках: старый поток закрывается,
    новый журнал создаётся в выбранной папке.
    """
    global _sink_id, _log_stream, _loguru_ready

    has_loguru = importlib.util.find_spec("loguru") is not None
    if has_loguru:
        from loguru import logger

        if not _loguru_ready:
            logger.remove()  # убираем консольный sink по умолчанию
            _loguru_ready = True
        if _sink_id is not None:
            logger.remove(_sink_id)

    if _log_stream is not None:
        _log_stream.close()

    stream = setup_log_file(path)
    # FFmpeg пишет напрямую в fd 2, минуя Python, — перенаправляем и его.
    os.dup2(stream.fileno(), 2)
    sys.stderr = stream

    if has_loguru:
        _sink_id = logger.add(stream, level="DEBUG", format=_LOG_FORMAT)
    _log_stream = stream
    return path
