"""Пример 3: Silero TTS (офлайн, torch).

Пакет silero-tts 0.0.5 не содержит __init__.py, поэтому обычный
`from silero_tts import SileroTTS` падает. Импортируем подмодуль напрямую.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".venv" / "Lib" / "site-packages"))

from silero_tts.silero_tts import SileroTTS  # noqa: E402

OUT = Path(r"C:\Users\bur_s\AppData\Local\Temp\opencode")

CASES = [
    ("ru", "v5_turkic", "Привет! Это офлайн синтез Silero."),
    ("en", "v3_en", "Hello! This is offline Silero synthesis."),
]

for lang, model_id, text in CASES:
    t0 = time.perf_counter()
    tts = SileroTTS(model_id=model_id, language=lang, sample_rate=24000)
    load_s = time.perf_counter() - t0

    dest = OUT / f"silero_{lang}.wav"
    t0 = time.perf_counter()
    tts.tts(text, str(dest))
    synth_s = time.perf_counter() - t0

    print(f"[OK] {lang}/{model_id}: загрузка {load_s:.1f}s, синтез {synth_s:.1f}s, "
          f"файл {dest.stat().st_size / 1024:.1f}KB")