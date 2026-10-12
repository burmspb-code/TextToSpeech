"""Общие пути для примеров в docs/.

Раньше здесь были захардкожены абсолютные пути вида
C:\\Users\\bur_s\\AppData\\Local\\Temp\\opencode — из-за этого примеры
работали только на одной машине.
"""
from pathlib import Path

# Корень проекта: docs/ -> ..
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Куда складывать сгенерированное аудио.
OUTPUT_DIR = PROJECT_ROOT / "output"

# Куда piper скачивает голоса.
VOICES_DIR = Path.home() / ".local" / "share" / "piper-voices"

# Базовый URL моделей Piper на Hugging Face.
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR