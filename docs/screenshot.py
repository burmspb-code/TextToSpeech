"""Открывает окно приложения и сохраняет его скриншот в output/.

    poetry run python docs/screenshot.py          — исходное состояние
    poetry run python docs/screenshot.py after    — после синтеза

Скриншот снимается через QWidget.grab(), поэтому окно может быть не видно.
"""
import sys
import time
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from texttospeech.app import TTSApp

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "output"
SAMPLE = OUT / "example.txt"


def make_sample() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(
        "Синтез речи из текста\n"
        "\n"
        "Этот текст будет озвучен встроенным движком Piper. "
        "Модель работает полностью офлайн: текст превращается в фонемы, "
        "а затем нейросеть генерирует звуковую волну.\n"
        "\n"
        "Проверка знаков: 0123456789 — «кавычки», тире, точка с запятой.\n",
        encoding="utf-8",
    )
    return SAMPLE


def wait_while_busy(window: TTSApp, qapp: QApplication, limit: float = 120.0) -> None:
    """Крутит цикл Qt, пока синтез не завершится."""
    deadline = time.monotonic() + limit
    while window.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def main() -> None:
    after_synthesis = "after" in sys.argv

    qapp = QApplication.instance() or QApplication(sys.argv)
    window = TTSApp()
    window.show()
    window._load_path(make_sample())

    if after_synthesis:
        window.raise_()
        window.activateWindow()
        window.on_synthesize()
        wait_while_busy(window, qapp)
        print(f"синтез завершён: {window.last_audio}")

    qapp.processEvents()
    window.raise_()
    window.activateWindow()

    dest = OUT / f"screenshot_gui{'_after' if after_synthesis else ''}.png"
    window.grab().save(str(dest))
    print(f"скриншот сохранён: {dest}")

    window.close()


if __name__ == "__main__":
    main()
