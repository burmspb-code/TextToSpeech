"""Пример 2: Piper (офлайн, ONNX) — рабочий синтез."""
from pathlib import Path
import wave

import requests

from piper import PiperVoice

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
CACHE = Path.home() / ".local" / "share" / "piper-voices"
OUT = Path(r"C:\Users\bur_s\AppData\Local\Temp\opencode")

VOICES = {
    "ru_RU-dmitri-medium": "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx",
    "en_US-ryan-medium": "en/en_US/ryan/medium/en_US-ryan-medium.onnx",
}


def fetch(rel: str) -> Path:
    dest = CACHE / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"скачиваю {rel} ...")
        with requests.get(f"{BASE}/{rel}", stream=True, timeout=120) as r:
            r.raise_for_status()
            dest.write_bytes(r.content)
    return dest


for name, rel in VOICES.items():
    model = fetch(rel)
    fetch(rel + ".json")
    size_mb = model.stat().st_size / 1024 / 1024

    text = "Привет, это офлайн синтез." if name.startswith("ru") else "Hello, this is offline synthesis."
    voice = PiperVoice.load(str(model))
    wav_path = OUT / f"piper_{name}.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    print(f"[OK] {name}  модель={size_mb:.1f}MB  wav={wav_path.stat().st_size / 1024:.1f}KB")