"""Открывает окно приложения и сохраняет его скриншот в output/.

    poetry run python docs/screenshot.py          — исходное состояние
    poetry run python docs/screenshot.py after    — после синтеза

Скриншот снимается экраном, поэтому окно должно быть видно: скрипт
поднимает его поверх остальных и снимает область окна.
"""
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

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


def capture(widget: tk.Misc, dest: Path) -> None:
    """Снимает область окна средствами Windows."""
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    w, h = widget.winfo_width(), widget.winfo_height()

    script = f"""
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {w}, {h}
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen({x}, {y}, 0, 0, $bmp.Size)
$bmp.Save('{dest}', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def run_event_loop(root: tk.Tk, predicate, limit: float = 120.0) -> None:
    """Крутит цикл Tkinter, пока предикат не станет истинным."""
    import time

    deadline = time.monotonic() + limit
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)


def main() -> None:
    after_synthesis = "after" in sys.argv

    root = tk.Tk()
    app = TTSApp(root)
    app._load_path(make_sample())

    if after_synthesis:
        root.attributes("-topmost", True)
        app.on_synthesize()
        run_event_loop(root, lambda: not app.busy)
        print(f"синтез завершён: {app.last_audio}")

    root.update_idletasks()
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()

    dest = OUT / f"screenshot_gui{'_after' if after_synthesis else ''}.png"
    capture(root, dest)
    print(f"скриншот сохранён: {dest}")

    root.destroy()


if __name__ == "__main__":
    main()