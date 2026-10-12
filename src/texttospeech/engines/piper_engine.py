"""Движок Piper: офлайн-синтез через ONNX Runtime."""
import re
import threading
import time
import wave
from pathlib import Path

from ..voices import Voice, download_voice
from .base import SynthesisResult

# Синтез Piper держит GIL, поэтому в одном процессе одновременно
# работает только один поток синтеза.
_SYNTH_LOCK = threading.Lock()


class PiperEngine:
    name = "Piper"
    offline = True

    def __init__(self) -> None:
        self._cache: dict[str, object] = {}

    def is_available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return True

    def prepare(self, voice: Voice, on_progress=None) -> None:
        """Скачивает модель, если её ещё нет на диске."""
        download_voice(voice, progress=on_progress)

    def _load(self, voice: Voice):
        """Загружает модель в память. Кэш — по ключу голоса."""
        if voice.key not in self._cache:
            from piper import PiperVoice

            self._cache[voice.key] = PiperVoice.load(str(voice.model_path))
        return self._cache[voice.key]

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Path,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Синтезирует текст в WAV-файл.

        speed > 1 — быстрее. Piper принимает обратную величину
        length_scale, поэтому делим 1.0 на speed.
        """
        if not self.is_available():
            from .base import EngineUnavailable

            raise EngineUnavailable("Пакет piper-tts не установлен")

        from piper import SynthesisConfig

        engine = self._load(voice)
        config = SynthesisConfig(length_scale=1.0 / max(speed, 0.1))

        dest.parent.mkdir(parents=True, exist_ok=True)

        started = time.perf_counter()
        with _SYNTH_LOCK:
            with wave.open(str(dest), "wb") as wav_file:
                engine.synthesize_wav(text, wav_file, syn_config=config)
        elapsed = time.perf_counter() - started

        with wave.open(str(dest)) as wav_file:
            duration = wav_file.getnframes() / wav_file.getframerate()

        return SynthesisResult(path=dest, duration=duration, audio_seconds=elapsed)


def split_text(text: str, limit: int = 600) -> list[str]:
    """Делит текст на фрагменты по границам предложений.

    Piper плохо справляется с очень длинными текстами: память растёт
    линейно, а качество падает. Дробление по предложениям решает обе
    проблемы и позволяет показывать прогресс.
    """
    text = text.strip()
    if not text:
        return []

    # Абзацы — жёсткая граница: не склеиваем разные абзацы в одно предложение.
    chunks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        sentences = re.split(r"(?<=[.!?…])\s+", paragraph)
        buffer = ""
        for sentence in sentences:
            # Если предложение само длиннее лимита — режем по словам.
            if len(sentence) > limit:
                if buffer:
                    chunks.append(buffer)
                    buffer = ""
                chunks.extend(_split_by_words(sentence, limit))
                continue

            if len(buffer) + len(sentence) + 1 <= limit:
                buffer = f"{buffer} {sentence}".strip()
            else:
                if buffer:
                    chunks.append(buffer)
                buffer = sentence

        if buffer:
            chunks.append(buffer)

    return chunks


def _split_by_words(text: str, limit: int) -> list[str]:
    """Аварийное деление слишком длинного предложения по словам."""
    words = text.split()
    chunks: list[str] = []
    buffer = ""
    for word in words:
        if len(buffer) + len(word) + 1 <= limit:
            buffer = f"{buffer} {word}".strip()
        else:
            if buffer:
                chunks.append(buffer)
            buffer = word
    if buffer:
        chunks.append(buffer)
    return chunks