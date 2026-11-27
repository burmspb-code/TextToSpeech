"""Пример: офлайн-синтез Silero голосом из каталога приложения.

Модели хранятся в ``models/silero``; SileroEngine подключает нужный .pt
к кэшу пакета silero-tts, поэтому пример работает без повторной загрузки.
"""
import time

from _common import ensure_output_dir

from texttospeech.engines import SileroEngine
from texttospeech.voices import find_voice

CASES = (
    ("silero-v5_5_ru-xenia-24000", "Привет! Это офлайн синтез Silero."),
    ("silero-v5_5_ru-aidar-24000", "Как дела? Это второй голос."),
)


def main() -> None:
    out_dir = ensure_output_dir()
    engine = SileroEngine()

    for key, text in CASES:
        voice = find_voice(key)
        t0 = time.perf_counter()
        engine.prepare(voice)
        load_s = time.perf_counter() - t0

        dest = out_dir / f"silero_{voice.name}.wav"
        t0 = time.perf_counter()
        engine.synthesize(text, voice, dest)
        synth_s = time.perf_counter() - t0

        size_kb = dest.stat().st_size / 1024
        print(
            f"[OK] {voice.title} ({key}): загрузка {load_s:.1f}s, "
            f"синтез {synth_s:.1f}s, файл {size_kb:.1f}KB  -> {dest}"
        )


if __name__ == "__main__":
    main()
