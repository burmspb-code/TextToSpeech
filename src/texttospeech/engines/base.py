"""Интерфейс движка синтеза.

Позволяет менять движок, не трогая интерфейс: сейчас есть Piper,
затем можно добавить edge-tts и Silero.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..voices import Voice


@dataclass(frozen=True)
class SynthesisResult:
    """Результат синтеза одного фрагмента."""

    path: Path  # куда записан звук
    duration: float  # длительность в секундах
    audio_seconds: float  # сколько времени занял синтез


class Engine(Protocol):
    """Движок, умеющий превращать текст в звук."""

    name: str
    #: Работает ли без интернета.
    offline: bool

    def is_available(self) -> bool:
        """Установлен ли этот движок в окружении."""
        ...

    def prepare(self, voice: Voice, on_progress=None) -> None:
        """Готовит голос: скачивает модель, если её нет."""
        ...

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Path,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Синтезирует текст и пишет WAV в dest."""
        ...


class EngineUnavailable(RuntimeError):
    """Движок не установлен в этом окружении."""