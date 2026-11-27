"""Скриншот интерфейса в состоянии несохранённых правок.

    poetry run python docs/screenshot_edit.py
"""
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from texttospeech.app import TTSApp

OUT = Path(__file__).resolve().parents[1] / "output"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    qapp = QApplication.instance() or QApplication([])
    window = TTSApp()
    window.show()

    sample = OUT / "example.txt"
    sample.write_text(
        "Синтез речи из текста\n"
        "\n"
        "Этот текст можно править прямо в окне. Всё, что вы напечатаете,\n"
        "попадёт в синтез — приложение читает поле, а не файл.\n"
        "\n"
        "Ctrl+S сохраняет правки обратно в файл.\n",
        encoding="utf-8",
    )
    window._load_path(sample)

    # Имитируем ввод: включаем несохранённые изменения.
    window.text_area.insertPlainText("\nПравка в окне — синтез её услышит.")
    qapp.processEvents()

    qapp.processEvents()
    window.raise_()
    window.activateWindow()

    dest = OUT / "screenshot_edit.png"
    window.grab().save(str(dest))
    print(f"скриншот сохранён: {dest}")

    window.close()


if __name__ == "__main__":
    main()
