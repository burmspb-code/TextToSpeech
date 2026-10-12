"""Графический интерфейс (Tkinter).

Заготовка: окно создаётся, синтез пока не подключён.
"""
import tkinter as tk
from tkinter import ttk

from . import __version__

APP_TITLE = "TextToSpeech"


def build_window() -> tk.Tk:
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("720x520")
    root.minsize(480, 400)

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=f"{APP_TITLE} {__version__}", font=("Segoe UI", 14, "bold")).pack(
        anchor="w"
    )
    ttk.Label(frame, text="Заготовка интерфейса — синтез ещё не подключён.").pack(
        anchor="w", pady=(16, 8)
    )

    text = tk.Text(frame, wrap="word", font=("Segoe UI", 11))
    text.pack(fill="both", expand=True)
    text.insert("1.0", "Привет! Это офлайн синтез речи на движке Piper.")

    return root


def main() -> None:
    build_window().mainloop()


if __name__ == "__main__":
    main()