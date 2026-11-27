"""Каталоги сгенерированных файлов внутри проекта."""
from pathlib import Path

# Корень проекта: src/texttospeech/paths.py -> ../..
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Готовые WAV, фрагменты и журнал лежат рядом с кодом проекта.
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_PATH = OUTPUT_DIR / "texttospeech.log"
