"""Движок Silero TTS: офлайн-синтез на PyTorch."""
import importlib.util
import threading
import time
import wave
from pathlib import Path

from ..audio import change_speed
from ..voices import (
    ProgressCallback,
    Voice,
    download_silero_model,
    expose_silero_model,
)
from .base import EngineUnavailable, SynthesisResult

# Silero держит GIL и не рассчитан на параллельный синтез.
_SYNTH_LOCK = threading.Lock()


class SileroEngine:
    name = "Silero"
    offline = True

    def __init__(self) -> None:
        # Одна .pt-модель обслуживает всех дикторов и частоты дискретизации.
        self._cache: dict[str, object] = {}

    def is_available(self) -> bool:
        """Проверяет пакет без тяжёлого импорта torch в GUI-потоке."""
        try:
            return importlib.util.find_spec("silero_tts.silero_tts") is not None
        except (ImportError, ValueError):
            return False

    def prepare(
        self, voice: Voice, on_progress: ProgressCallback | None = None
    ) -> None:
        """Скачивает модель при необходимости и держит её загруженной."""
        if not self.is_available():
            raise EngineUnavailable("пакет silero-tts не установлен")
        if not voice.is_downloaded:
            download_silero_model(voice, progress=on_progress)
        expose_silero_model(voice)
        self._load(voice)

    def _load(self, voice: Voice) -> object:
        """Загружает .pt-модель в память, по разу на модель."""
        key = voice.model_id
        if key not in self._cache:
            # silero-tts ищет .pt в site-packages — подключаем модель из
            # папки проекта перед созданием библиотечного объекта.
            expose_silero_model(voice)
            # В silero-tts 0.0.5 нет __init__.py, поэтому импортируем подмодуль.
            from silero_tts.silero_tts import SileroTTS

            with _SYNTH_LOCK:
                if key not in self._cache:
                    self._cache[key] = SileroTTS(
                        model_id=voice.model_id,
                        language="ru",
                        speaker=voice.speaker,
                        sample_rate=voice.sample_rate,
                    )
        return self._cache[key]

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Path,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Синтезирует текст в WAV.

        Silero не принимает скорость: при speed != 1 звук проходит через
        phase vocoder, который меняет длительность без сдвига высоты тона.
        """
        if not self.is_available():
            raise EngineUnavailable("пакет silero-tts не установлен")

        tts = self._load(voice)
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(f"{dest.stem}.raw.wav") if speed != 1.0 else dest

        started = time.perf_counter()
        available_speakers = set(tts.get_available_speakers())  # type: ignore[attr-defined]
        available_rates = set(tts.get_available_sample_rates())  # type: ignore[attr-defined]
        if voice.speaker not in available_speakers:
            raise ValueError(
                f"Диктор {voice.speaker} отсутствует в модели {voice.model_id}: "
                f"{sorted(available_speakers)}"
            )
        if voice.sample_rate not in available_rates:
            raise ValueError(
                f"Частота {voice.sample_rate} недоступна в модели {voice.model_id}"
            )

        with _SYNTH_LOCK:
            # Диктор и качество меняются на одной загруженной модели.
            tts.speaker = voice.speaker  # type: ignore[attr-defined]
            tts.sample_rate = voice.sample_rate  # type: ignore[attr-defined]
            tts.tts(text, str(temp))  # type: ignore[attr-defined]

        # silero-tts при ошибке диктора пишет пустой WAV и не бросает
        # исключение — без этой проверки пользователь получил тишину.
        with wave.open(str(temp)) as wav_file:
            if wav_file.getnframes() == 0:
                raise RuntimeError(
                    f"Silero не создал звук для голоса {voice.title}: "
                    "проверьте текст и диктора"
                )

        if speed != 1.0:
            change_speed(temp, dest, speed)
            temp.unlink(missing_ok=True)
        elapsed = time.perf_counter() - started

        with wave.open(str(dest)) as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()

        return SynthesisResult(path=dest, duration=duration, audio_seconds=elapsed)
