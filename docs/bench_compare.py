"""Head-to-head: Piper vs Silero на одинаковом тексте."""
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".venv" / "Lib" / "site-packages"))

import numpy as np  # noqa: E402
from piper import PiperVoice  # noqa: E402
from silero_tts.silero_tts import SileroTTS  # noqa: E402

OUT = Path(r"C:\Users\bur_s\AppData\Local\Temp\opencode")
CACHE = Path.home() / ".local/share/piper-voices"

TEXT = (
    "Привет! Это сравнение двух офлайн движков синтеза речи. "
    "Piper работает на оннекс, а Silero использует нейросеть на PyTorch."
)


def measure(path: Path, synth_s: float) -> tuple[float, float]:
    with wave.open(str(path)) as w:
        dur = w.getnframes() / w.getframerate()
        rate = w.getframerate()
    return dur, synth_s / dur


def bench_piper(model: Path, dest: Path) -> None:
    voice = PiperVoice.load(str(model))
    t0 = time.perf_counter()
    with wave.open(str(dest), "wb") as w:
        voice.synthesize_wav(TEXT, w)
    dur, rtf = measure(dest, time.perf_counter() - t0)
    print(f"Piper  ru (dmitri) : {dur:5.2f}s аудио, RTF={rtf:.3f}, {dest.stat().st_size / 1024:6.1f}KB, 22050 Hz")


def bench_silero(model_id: str, lang: str, dest: Path) -> None:
    tts = SileroTTS(model_id=model_id, language=lang, sample_rate=24000)
    t0 = time.perf_counter()
    tts.tts(TEXT, str(dest))
    dur, rtf = measure(dest, time.perf_counter() - t0)
    print(f"Silero ru ({model_id}): {dur:5.2f}s аудио, RTF={rtf:.3f}, {dest.stat().st_size / 1024:6.1f}KB, 24000 Hz")


bench_piper(
    CACHE / "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx",
    OUT / "cmp_piper_ru.wav",
)
bench_silero("v5_turkic", "ru", OUT / "cmp_silero_ru.wav")

print()
print("Качество сигнала (RMS, чем ближе к типичной речи — тем лучше):")
for p in (OUT / "cmp_piper_ru.wav", OUT / "cmp_silero_ru.wav"):
    with wave.open(str(p)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    print(f"  {p.name:18s} RMS={np.sqrt((a**2).mean()):8.1f}  peak={np.abs(a).max():6.0f}")