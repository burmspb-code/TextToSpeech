"""Открывает окно приложения и сохраняет его скриншот в output/.

Запуск:  poetry run python docs/screenshot.py
"""
from pathlib import Path

import tkinter as tk

from texttospeech.app import TTSApp

OUT = Path(__file__).resolve().parents[1] / "output"
SAMPLE = "example.txt"


def make_sample() -> Path:
    path = OUT / SAMPLE
    path.write_text(
        "Синтез речи из текста\n"
        "\n"
        "Этот текст будет озвучен встроенным движком Piper. "
        "Модель работает полностью офлайн: текст превращается в фонемы, "
        "а затем нейросеть генерирует звуковую волну.\n"
        "\n"
        "Проверка знаков: 0123456789 — «кавычки», тире, точка с запятой.\n",
        encoding="utf-8",
    )
    return path


def capture(widget: tk.Misc, dest: Path) -> None:
    """Сохраняет снимок области окна через Pillow-free код PowerShell."""
    import subprocess
    import sys

    x = widget.winfo_rootx()
    y = widget.winfo_rooty()
    w = widget.winfo_width()
    h = widget.winfo_height()

    script = f"""
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {w}, {h}
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen({x}, {y}, 0, 0, $bmp.Size)
$bmp.Save('{dest}', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    app = TTSApp(root)
    app._load_path(make_sample())

    root.update_idletasks()
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()

    dest = OUT / "screenshot_gui.png"
    capture(root, dest)
    print(f"скриншот сохранён: {dest}")

    root.destroy()


if __name__ == "__main__":
    main()