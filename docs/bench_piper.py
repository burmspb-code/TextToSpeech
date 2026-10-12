"""Замер скорости Piper: реальное время против времени синтеза (RTF)."""
import time
import wave

from piper import PiperVoice

from _common import VOICES_DIR, ensure_output_dir

MODEL = VOICES_DIR / "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"
TEXT = "Привет! Это проверка скорости синтеза на достаточно длинном тексте. " * 5


def main() -> None:
    out = ensure_output_dir() / "piper_speed.wav"

    t0 = time.perf_counter()
    voice = PiperVoice.load(str(MODEL))
    load_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    with wave.open(str(out), "wb") as w:
        voice.synthesize_wav(TEXT, w)
    synth_s = time.perf_counter() - t0

    with wave.open(str(out)) as w:
        dur = w.getnframes() / w.getframerate()
        rate, ch, samp = w.getframerate(), w.getnchannels(), w.getsampwidth()

    print(f"загрузка модели : {load_s:.2f} c")
    print(f"синтез          : {synth_s:.2f} c")
    print(f"длительность    : {dur:.2f} c аудио")
    print(f"RTF             : {synth_s / dur:.3f}  (меньше 1 = быстрее реального времени)")
    print(f"формат          : {rate} Hz, {ch} ch, {samp * 8} bit")


if __name__ == "__main__":
    main()