"""Скриншот интерфейса в состоянии несохранённых правок.

    poetry run python docs/screenshot_edit.py
"""
import subprocess
from pathlib import Path

import tkinter as tk

from texttospeech.app import TTSApp

OUT = Path(__file__).resolve().parents[1] / "output"


def capture(widget: tk.Misc, dest: Path) -> None:
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    app = TTSApp(root)

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
    app._load_path(sample)

    # Имитируем ввод: включаем несохранённые изменения.
    app.text_area.insert("end", "\nПравка в окне — синтез её услышит.")
    app.text_area.edit_modified(True)
    app._on_text_modified()

    root.update_idletasks()
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.update()

    dest = OUT / "screenshot_edit.png"
    capture(root, dest)
    print(f"скриншот сохранён: {dest}")

    root.destroy()


if __name__ == "__main__":
    main()