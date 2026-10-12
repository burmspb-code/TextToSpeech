"""Пример: Piper (офлайн, ONNX) — скачивание модели и синтез."""
import wave

import requests
from piper import PiperVoice

from _common import HF_BASE, VOICES_DIR, ensure_output_dir

VOICES = {
    "ru_RU-dmitri-medium": "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx",
    "en_US-ryan-medium": "en/en_US/ryan/medium/en_US-ryan-medium.onnx",
}

TEXTS = {
    "ru": "Привет, это офлайн синтез.",
    "en": "Hello, this is offline synthesis.",
}


def fetch(rel: str) -> None:
    """Скачивает файл модели, если его ещё нет."""
    dest = VOICES_DIR / rel
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"скачиваю {rel} ...")
    with requests.get(f"{HF_BASE}/{rel}", stream=True, timeout=300) as r:
        r.raise_for_status()
        dest.write_bytes(r.content)


def main() -> None:
    out_dir = ensure_output_dir()

    for name, rel in VOICES.items():
        fetch(rel)
        fetch(rel + ".json")  # конфиг с фонемами и id-картой
        model = VOICES_DIR / rel

        lang = rel.split("/")[0][:2]
        text = TEXTS[lang]

        voice = PiperVoice.load(str(model))
        wav_path = out_dir / f"piper_{name}.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

        size_mb = model.stat().st_size / 1024 / 1024
        size_kb = wav_path.stat().st_size / 1024
        print(f"[OK] {name}  модель={size_mb:.1f}MB  wav={size_kb:.1f}KB  -> {wav_path}")


if __name__ == "__main__":
    main()