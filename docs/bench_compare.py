"""Head-to-head: Piper против Silero на одинаковом тексте.

Нужен оба движка: poetry install --with silero
"""
import time
import wave

import numpy as np
from piper import PiperVoice
from silero_tts.silero_tts import SileroTTS

from _common import VOICES_DIR, ensure_output_dir

TEXT = (
    "Привет! Это сравнение двух офлайн движков синтеза речи. "
    "Piper работает на оннекс, а Silero использует нейросеть на PyTorch."
)


def measure(path, synth_s: float) -> tuple[float, float]:
    """Возвращает (длительность аудио, RTF)."""
    with wave.open(str(path)) as w:
        dur = w.getnframes() / w.getframerate()
    return dur, synth_s / dur


def main() -> None:
    out_dir = ensure_output_dir()

    # --- Piper ---
    piper_wav = out_dir / "cmp_piper_ru.wav"
    voice = PiperVoice.load(str(VOICES_DIR / "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"))
    t0 = time.perf_counter()
    with wave.open(str(piper_wav), "wb") as w:
        voice.synthesize_wav(TEXT, w)
    dur, rtf = measure(piper_wav, time.perf_counter() - t0)
    print(f"Piper  ru (dmitri)    : {dur:5.2f}s аудио, RTF={rtf:.3f}, "
          f"{piper_wav.stat().st_size / 1024:6.1f}KB, 22050 Hz")

    # --- Silero ---
    silero_wav = out_dir / "cmp_silero_ru.wav"
    tts = SileroTTS(model_id="v5_turkic", language="ru", sample_rate=24000)
    t0 = time.perf_counter()
    tts.tts(TEXT, str(silero_wav))
    dur, rtf = measure(silero_wav, time.perf_counter() - t0)
    print(f"Silero ru (v5_turkic) : {dur:5.2f}s аудио, RTF={rtf:.3f}, "
          f"{silero_wav.stat().st_size / 1024:6.1f}KB, 24000 Hz")

    # --- Уровень сигнала ---
    print()
    print("Уровень сигнала (RMS; выше — громче и разборчивее):")
    for path in (piper_wav, silero_wav):
        with wave.open(str(path)) as w:
            samples = np.frombuffer(
                w.readframes(w.getnframes()), dtype=np.int16
            ).astype(np.float32)
        rms = float(np.sqrt((samples**2).mean()))
        print(f"  {path.name:20s} RMS={rms:8.1f}  peak={float(np.abs(samples).max()):6.0f}")


if __name__ == "__main__":
    main()