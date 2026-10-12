"""Пример: Silero TTS (офлайн, torch).

Пакет silero-tts 0.0.5 не содержит __init__.py, поэтому
`from silero_tts import SileroTTS` падает с ImportError.
Работает прямой импорт подмодуля — он разрешается как namespace-пакет.
"""
import time

from silero_tts.silero_tts import SileroTTS

from _common import ensure_output_dir

CASES = [
    ("ru", "v5_turkic", "Привет! Это офлайн синтез Silero."),
    ("en", "v3_en", "Hello! This is offline Silero synthesis."),
]


def main() -> None:
    out_dir = ensure_output_dir()

    for lang, model_id, text in CASES:
        t0 = time.perf_counter()
        tts = SileroTTS(model_id=model_id, language=lang, sample_rate=24000)
        load_s = time.perf_counter() - t0

        dest = out_dir / f"silero_{lang}.wav"
        t0 = time.perf_counter()
        tts.tts(text, str(dest))
        synth_s = time.perf_counter() - t0

        size_kb = dest.stat().st_size / 1024
        print(f"[OK] {lang}/{model_id}: загрузка {load_s:.1f}s, "
              f"синтез {synth_s:.1f}s, файл {size_kb:.1f}KB  -> {dest}")


if __name__ == "__main__":
    main()