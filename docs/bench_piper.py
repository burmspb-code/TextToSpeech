"""Замер скорости Piper: реальное время vs время синтеза (RTF)."""
import time
import wave
from pathlib import Path

from piper import PiperVoice

MODEL = Path.home() / ".local/share/piper-voices/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"
TEXT = "Привет! Это проверка скорости синтеза на reasonably длинном тексте. " * 5

t0 = time.perf_counter()
voice = PiperVoice.load(str(MODEL))
load_s = time.perf_counter() - t0

out = Path(r"C:\Users\bur_s\AppData\Local\Temp\opencode\piper_speed.wav")
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