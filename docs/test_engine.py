"""Проверка движка Piper и деления текста до подключения к GUI."""
from pathlib import Path

from texttospeech.engines import PiperEngine, split_text
from texttospeech.voices import find_voice

# --- Деление текста ---
short = "Привет. Как дела? Всё хорошо!"
print(f"короткий  -> {len(split_text(short))} фрагм.")
for chunk in split_text(short):
    print(f"   {chunk!r}")

long_text = ("Это первое предложение. " * 30) + " " + ("А вот ещё одно." * 50)
parts = split_text(long_text)
print(f"\nдлинный   -> {len(parts)} фрагм., макс. длина {max(len(p) for p in parts)}")

huge = "слово " * 1000
parts = split_text(huge)
print(f"огромный  -> {len(parts)} фрагм., макс. длина {max(len(p) for p in parts)}")

print(f"\nпустой    -> {split_text('')}")
print(f"абзацы    -> {len(split_text('Первый.\n\nВторой.'))} фрагм.")

# --- Синтез ---
voice = find_voice("ru_RU-dmitri-medium")
print(f"\nголос: {voice.key} | {voice.title} | скачан: {voice.is_downloaded}")

engine = PiperEngine()
print(f"движок {engine.name}, офлайн={engine.offline}, доступен={engine.is_available()}")

out = Path("output") / "engine_test.wav"
result = engine.synthesize("Проверка движка Piper из модуля.", voice, out, speed=1.0)
print(f"синтез: {result.duration:.2f} c аудио за {result.audio_seconds:.2f} c")

fast = engine.synthesize("Проверка скорости.", voice, Path("output") / "engine_fast.wav", speed=2.0)
print(f"speed=2.0: {fast.duration:.2f} c аудио (против 2.3 c на скорости 1.0)")