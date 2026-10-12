"""Графический интерфейс (Tkinter), светлая тема.

Состояние заготовки: файл открывается и показывается, кнопка «Озвучить»
пока ничего не синтезирует.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import __version__

# --- Палитра светлой темы ---
BG = "#F4F6F8"        # фон окна
SURFACE = "#FFFFFF"   # карточки и поля
TEXT = "#1F2328"      # основной текст
TEXT_DIM = "#656D76"  # второстепенный текст
BORDER = "#D5DBE1"    # рамки
ACCENT = "#2F6FEB"    # основной акцент
ACCENT_HOVER = "#2560D4"
ACCENT_ACTIVE = "#1D4FB8"
DANGER = "#CF222E"

FONT = "Segoe UI"
FONT_SIZE = 10

# Файлы, которые имеет смысл открывать.
FILE_TYPES = [
    ("Текстовые файлы", "*.txt *.md *.text"),
    ("Все файлы", "*.*"),
]

# Кодировки для чтения. Русские тексты часто лежат в windows-1251.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1251", "latin-1")


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    """Выбирает падеж: 1 символ, 2 символа, 5 символов."""
    n = abs(number) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def read_text_file(path: Path) -> tuple[str, str]:
    """Читает файл, перебирая кодировки. Возвращает (текст, кодировка)."""
    raw = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Не удалось определить кодировку файла {path.name}")


def setup_styles(root: tk.Tk) -> None:
    """Настраивает виджеты под светлую тему."""
    style = ttk.Style(root)
    # «clam» — единственная тема ttk, где цвета задаются вручную.
    style.theme_use("clam")

    root.option_add("*Font", (FONT, FONT_SIZE))

    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=SURFACE, relief="flat")

    style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, FONT_SIZE))
    style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("Dim.TLabel", background=SURFACE, foreground=TEXT_DIM)
    style.configure("BgDim.TLabel", background=BG, foreground=TEXT_DIM)
    style.configure(
        "Title.TLabel",
        background=SURFACE,
        foreground=TEXT,
        font=(FONT, 15, "bold"),
    )
    style.configure("Status.TLabel", background=BG, foreground=TEXT_DIM, font=(FONT, 9))

    style.configure(
        "TButton",
        background=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        focuscolor=SURFACE,
        padding=(14, 8),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", "#EAEEF2"), ("disabled", BG)],
        foreground=[("disabled", "#A8B0B8")],
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="#FFFFFF",
        bordercolor=ACCENT,
        focuscolor=ACCENT,
        font=(FONT, FONT_SIZE, "bold"),
        padding=(22, 9),
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_ACTIVE), ("disabled", "#B6C6E4")],
        foreground=[("disabled", "#EEF2F9")],
    )

    style.configure(
        "TCombobox",
        fieldbackground=SURFACE,
        background=SURFACE,
        foreground=TEXT,
        bordercolor=BORDER,
        arrowcolor=TEXT,
        padding=(8, 6),
    )
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)])

    style.configure("TSeparator", background=BORDER)


class TTSApp:
    """Окно приложения."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.current_path: Path | None = None
        # Сохраняем ссылку, чтобы тесты и внешний код находили приложение.
        root.tts_app = self

        root.title(f"TextToSpeech {__version__}")
        root.geometry("860x620")
        root.minsize(640, 480)
        root.configure(bg=BG)

        setup_styles(root)
        self._build()
        self.set_status("Готов. Откройте текстовый файл.")

    # --- Построение интерфейса ---

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        self._build_header(outer)
        self._build_toolbar(outer)
        self._build_content(outer)
        self._build_controls(outer)
        self._build_statusbar(outer)

    def _build_header(self, parent: tk.Widget) -> None:
        header = ttk.Frame(parent, style="Surface.TFrame", padding=(18, 14))
        header.pack(fill="x")
        header.configure(style="Surface.TFrame")

        ttk.Label(header, text="TextToSpeech", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Офлайн-синтез речи на движке Piper",
            style="Dim.TLabel",
        ).pack(side="left", padx=(12, 0), pady=(4, 0))

    def _build_toolbar(self, parent: tk.Widget) -> None:
        bar = ttk.Frame(parent, style="Surface.TFrame", padding=(18, 10))
        bar.pack(fill="x", pady=(10, 0))

        ttk.Button(bar, text="Открыть файл", command=self.open_file).pack(side="left")

        self.path_label = ttk.Label(bar, text="Файл не выбран", style="Dim.TLabel")
        self.path_label.pack(side="left", padx=(14, 0))

        ttk.Button(bar, text="Очистить", command=self.clear_file).pack(side="right")

    def _build_content(self, parent: tk.Widget) -> None:
        wrapper = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        wrapper.pack(fill="both", expand=True, pady=10)

        self.text_area = tk.Text(
            wrapper,
            width=80,
            # Высоту задаём минимальной — реальный размер даёт
            # pack(expand=True). Со значением по умолчанию (24 строки)
            # панель управления выдавливалась за пределы окна.
            height=1,
            wrap="word",
            bg=SURFACE,
            fg=TEXT,
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=14,
            font=(FONT, 11),
            insertbackground=TEXT,
            selectbackground="#CCE0FF",
            highlightthickness=0,
        )
        self.text_area.pack(fill="both", expand=True)
        self.text_area.configure(state="disabled")

    def _build_controls(self, parent: tk.Widget) -> None:
        panel = ttk.Frame(parent, style="Surface.TFrame", padding=(18, 12))
        panel.pack(fill="x")

        ttk.Label(panel, text="Голос", style="Dim.TLabel").pack(side="left")

        self.voice_box = ttk.Combobox(
            panel,
            values=["ru_RU dmitri", "ru_RU irina", "en_US ryan"],
            state="readonly",
            width=22,
        )
        self.voice_box.set("ru_RU dmitri")
        self.voice_box.pack(side="left", padx=(8, 20))

        ttk.Label(panel, text="Скорость", style="Dim.TLabel").pack(side="left")

        self.speed_box = ttk.Combobox(
            panel,
            values=["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"],
            state="readonly",
            width=8,
        )
        self.speed_box.set("1.0x")
        self.speed_box.pack(side="left", padx=(8, 0))

        self.speak_button = ttk.Button(
            panel,
            text="Озвучить",
            style="Accent.TButton",
            command=self.on_synthesize,
        )
        self.speak_button.pack(side="right")

    def _build_statusbar(self, parent: tk.Widget) -> None:
        self.status_label = ttk.Label(parent, text="", style="Status.TLabel")
        self.status_label.pack(fill="x", pady=(10, 0))

    # --- Действия ---

    def open_file(self) -> None:
        """Показывает диалог выбора файла и загружает выбранный."""
        selected = filedialog.askopenfilename(
            title="Открыть текстовый файл",
            filetypes=FILE_TYPES,
        )
        if not selected:
            return
        self._load_path(Path(selected))

    def _load_path(self, path: Path) -> None:
        """Читает файл и показывает его содержимое."""
        try:
            content, encoding = read_text_file(path)
        except (OSError, ValueError) as exc:
            self.set_status(f"Не удалось прочитать файл: {exc}", error=True)
            return

        self.current_path = path
        self.path_label.configure(text=f"{path.name}  ({encoding})")

        self._set_text(content)

        words = len(content.split())
        self.set_status(
            f"Загружено: {len(content)} "
            f"{plural_ru(len(content), 'символ', 'символа', 'символов')}, "
            f"{words} {plural_ru(words, 'слово', 'слова', 'слов')}."
        )

    def _set_text(self, content: str) -> None:
        """Подставляет текст в поле, сохраняя его нередактируемым."""
        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", content)
        self.text_area.configure(state="disabled")

    def clear_file(self) -> None:
        self.current_path = None
        self.path_label.configure(text="Файл не выбран")
        self._set_text("")
        self.set_status("Файл очищен.")

    def on_synthesize(self) -> None:
        """Заглушка: синтез подключим следующим шагом."""
        if self.current_path is None:
            self.set_status("Сначала откройте файл.", error=True)
            return
        self.set_status("Синтез пока не подключён — это следующий шаг.")

    def set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=text,
            foreground=DANGER if error else TEXT_DIM,
        )


def build_window() -> tk.Tk:
    root = tk.Tk()
    TTSApp(root)
    return root


def main() -> None:
    build_window().mainloop()


if __name__ == "__main__":
    main()