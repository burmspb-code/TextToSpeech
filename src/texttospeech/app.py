"""Графический интерфейс (Tkinter), светлая тема.

Синтез выполняется в отдельном потоке: работа движка занимает секунды,
и главный поток Tkinter всё это время должен оставаться отзывчивым.
Результаты потока возвращаются в очередь и разбираются через after().
"""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .audio import Player, concat_wavs
from .engines import PiperEngine, split_text
from .voices import (
    CATALOG,
    DEFAULT_VOICE_KEY,
    Voice,
    find_voice,
    find_voice_by_label,
    voice_size_mb,
)

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
SUCCESS = "#1A7F37"

# Куда складываются готовые дорожки.
OUTPUT_DIR = Path.home() / ".local" / "share" / "texttospeech"

FONT = "Segoe UI"
FONT_SIZE = 10

# Файлы, которые имеет смысл открывать.
FILE_TYPES = [
    ("Текстовые файлы", "*.txt *.md *.text"),
    ("Все файлы", "*.*"),
]

# Кодировки для чтения. Русские тексты часто лежат в windows-1251.
ENCODINGS = ("utf-8", "cp1251", "latin-1")

# BOM utf-8 проверяем отдельно: кодировка utf-8-sig декодирует любой
# utf-8 без ошибок, поэтому в общем списке она помечала бы обычный
# файл как имеющий BOM, а при сохранении добавила бы лишние байты.
UTF8_BOM = b"\xef\xbb\xbf"


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
    """Читает файл, перебирая кодировки. Возвращает (текст, кодировка).

    Кодировка возвращается именно в том виде, в каком файл нужно будет
    записать обратно — чтобы правки не поменяли кодировку файла.
    """
    raw = path.read_bytes()

    if raw.startswith(UTF8_BOM):
        return raw[len(UTF8_BOM):].decode("utf-8"), "utf-8-sig"

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
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=BORDER,
        bordercolor=BORDER,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
    )

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
        # Кодировка файла нужна, чтобы сохранить правки в том же формате.
        self.current_encoding: str | None = None
        # Правки пользователя не сохранены на диск.
        self.dirty = False
        # Пока идёт загрузка файла, правки не считаются пользовательскими.
        self._loading = False
        # Сохраняем ссылку, чтобы тесты и внешний код находили приложение.
        root.tts_app = self

        root.title(f"TextToSpeech {__version__}")
        root.geometry("860x620")
        root.minsize(640, 520)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.engine = PiperEngine()
        self.player = Player()
        self.last_audio: Path | None = None
        self.busy = False
        # Поток докладывает о ходе дела сюда, главный поток забирает
        # через after(). Обмен через очередь — единственный безопасный
        # способ передачи данных между потоками в Tkinter.
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None

        setup_styles(root)
        self._build()
        self._update_title()
        self.set_status("Готов. Откройте файл или введите текст в поле ниже.")

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

        self.save_button = ttk.Button(
            bar, text="Сохранить", command=self.save_file, state="disabled"
        )
        self.save_button.pack(side="right", padx=(0, 8))

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
            insertwidth=2,
            selectbackground="#CCE0FF",
            highlightthickness=0,
            undo=True,
        )

        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.text_area.pack(side="left", fill="both", expand=True)

        # Поле редактируемое: >>Modified>> срабатывает на любое изменение.
        self.text_area.bind("<<Modified>>", self._on_text_modified)
        self.text_area.bind("<Control-s>", lambda _e: (self.save_file(), "break")[1])
        self.text_area.bind("<Control-o>", lambda _e: (self.open_file(), "break")[1])

    def _build_controls(self, parent: tk.Widget) -> None:
        panel = ttk.Frame(parent, style="Surface.TFrame", padding=(18, 12))
        panel.pack(fill="x")

        ttk.Label(panel, text="Голос", style="Dim.TLabel").pack(side="left")

        self.voice_box = ttk.Combobox(
            panel,
            values=[v.label for v in CATALOG],
            state="readonly",
            width=22,
        )
        self.voice_box.set(self._label_of(DEFAULT_VOICE_KEY))
        self.voice_box.pack(side="left", padx=(8, 16))
        self.voice_box.bind("<<ComboboxSelected>>", lambda _e: self._on_voice_changed())

        ttk.Label(panel, text="Скорость", style="Dim.TLabel").pack(side="left")

        self.speed_box = ttk.Combobox(
            panel,
            values=["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"],
            state="readonly",
            width=7,
        )
        self.speed_box.set("1.0x")
        self.speed_box.pack(side="left", padx=(8, 16))

        self.play_button = ttk.Button(
            panel,
            text="Стоп",
            command=self.stop_playback,
            state="disabled",
        )
        self.play_button.pack(side="right", padx=(0, 8))

        self.speak_button = ttk.Button(
            panel,
            text="Озвучить",
            style="Accent.TButton",
            command=self.on_synthesize,
        )
        self.speak_button.pack(side="right")

        self.progress = ttk.Progressbar(panel, mode="determinate", length=160)
        self.progress.pack(side="right", padx=(0, 16))
        self.progress.pack_forget()

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
        if not self._confirm_discard("Открыть другой файл?"):
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
        self.current_encoding = encoding
        self._set_text(content)
        self._set_dirty(False)
        self._refresh_path_label()

        words = len(content.split())
        self.set_status(
            f"Загружено: {len(content)} "
            f"{plural_ru(len(content), 'символ', 'символа', 'символов')}, "
            f"{words} {plural_ru(words, 'слово', 'слова', 'слов')}."
        )

    def _set_text(self, content: str) -> None:
        """Подставляет текст в поле."""
        self._loading = True
        try:
            self.text_area.configure(state="normal")
            self.text_area.delete("1.0", "end")
            self.text_area.insert("1.0", content)
            # Сбрасываем флаг: иначе следующая же правка не даст события.
            self.text_area.edit_modified(False)
        finally:
            self._loading = False

    @property
    def current_text(self) -> str:
        """Актуальный текст из поля — единственный источник истины."""
        return self.text_area.get("1.0", "end-1c")

    # --- Правки и сохранение ---

    def _on_text_modified(self, _event: tk.Event | None = None) -> None:
        if not self.text_area.edit_modified():
            return
        # Флаг служит только сигналом для нас — сбрасываем сразу.
        self.text_area.edit_modified(False)
        if self._loading or self.dirty:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.save_button.configure(state="normal" if dirty else "disabled")
        self._update_title()
        self._refresh_path_label()

    def _update_title(self) -> None:
        if self.current_path:
            mark = " *" if self.dirty else ""
            self.root.title(f"{self.current_path.name}{mark} — TextToSpeech {__version__}")
        else:
            self.root.title(f"TextToSpeech {__version__}")

    def _refresh_path_label(self) -> None:
        if self.current_path is None:
            self.path_label.configure(text="Новый текст")
            return
        parts = [self.current_path.name]
        if self.current_encoding:
            parts.append(self.current_encoding)
        if self.dirty:
            parts.append("изменён")
        self.path_label.configure(text=" · ".join(parts))

    def save_file(self) -> None:
        """Сохраняет текст в файл; если файла нет — спрашивает имя."""
        path = self.current_path
        if path is None:
            path = self._ask_save_path()
            if path is None:
                return

        try:
            path.write_text(self.current_text, encoding=self.current_encoding or "utf-8")
        except OSError as exc:
            self.set_status(f"Не удалось сохранить: {exc}", error=True)
            return

        self.current_path = path
        self._set_dirty(False)
        self.set_status(f"Сохранено: {path.name}", success=True)

    def _ask_save_path(self) -> Path | None:
        selected = filedialog.asksaveasfilename(
            title="Сохранить текст",
            defaultextension=".txt",
            filetypes=FILE_TYPES,
        )
        return Path(selected) if selected else None

    def _confirm_discard(self, action: str) -> bool:
        """Спрашивает, что делать с несохранёнными правками.

        True — можно продолжать, False — пользователь передумал.
        """
        if not self.dirty:
            return True

        answer = messagebox.askyesnocancel(
            "Несохранённые изменения",
            f"{action}\n\nТекст изменён, изменения не сохранены.",
            parent=self.root,
        )
        if answer is None:
            return False
        if answer:
            self.save_file()
            return not self.dirty
        return True

    def clear_file(self) -> None:
        if not self._confirm_discard("Очистить поле?"):
            return

        self.player.stop()
        self.current_path = None
        self.current_encoding = None
        self._set_text("")
        self._set_dirty(False)
        self.set_status("Поле очищено.")

    def on_close(self) -> None:
        if self._confirm_discard("Закрыть программу?"):
            self.player.stop()
            self.root.destroy()

    # --- Голос и скорость ---

    @staticmethod
    def _label_of(key: str) -> str:
        return find_voice(key).label

    @property
    def selected_voice(self) -> Voice:
        return find_voice_by_label(self.voice_box.get())

    @property
    def selected_speed(self) -> float:
        return float(self.speed_box.get().rstrip("x"))

    def _on_voice_changed(self) -> None:
        voice = self.selected_voice
        if voice.is_downloaded:
            self.set_status(f"Голос {voice.title} уже загружен.")
        else:
            mb = voice_size_mb(voice)
            self.set_status(f"Голос {voice.title} будет скачан при синтезе (~{mb:.0f} МБ).")

    # --- Синтез ---

    def on_synthesize(self) -> None:
        """Запускает синтез в фоновом потоке."""
        if self.busy:
            return
        if not self.current_text.strip():
            self.set_status("Сначала откройте файл с текстом.", error=True)
            return
        if not self.engine.is_available():
            self.set_status("Пакет piper-tts не установлен.", error=True)
            return

        voice = self.selected_voice
        speed = self.selected_speed

        self._set_busy(True)
        self.player.stop()
        self.progress.configure(value=0, maximum=100)
        self.progress.pack(side="right", padx=(0, 16))

        if voice.is_downloaded:
            self.set_status(f"Синтез голосом {voice.title}...")
        else:
            self.set_status(f"Скачиваю голос {voice.title} (~60 МБ)...")

        self._worker = threading.Thread(
            target=self._synthesize_worker,
            args=(self.current_text, voice, speed),
            daemon=True,
        )
        self._worker.start()
        self._poll_events()

    def _synthesize_worker(self, text: str, voice: Voice, speed: float) -> None:
        """Синтез в отдельном потоке. Всё общение с UI — через очередь."""
        try:
            if not voice.is_downloaded:
                def on_progress(done: int, total: int) -> None:
                    if total:
                        percent = min(100, done * 100 // total)
                        self.events.put(("download", percent))

                self.events.put(("status", f"Скачиваю голос {voice.title}..."))
                self.engine.prepare(voice, on_progress=on_progress)

            chunks = split_text(text)
            if not chunks:
                self.events.put(("error", "В файле нет текста для синтеза."))
                return

            parts_dir = OUTPUT_DIR / "parts"
            parts_dir.mkdir(parents=True, exist_ok=True)

            results = []
            for index, chunk in enumerate(chunks, start=1):
                part = parts_dir / f"part_{index:04d}.wav"
                self.events.put(("progress", index * 100 // len(chunks)))
                results.append(
                    self.engine.synthesize(chunk, voice, part, speed=speed).path
                )

            dest = OUTPUT_DIR / f"{voice.key}_{speed:g}x.wav"
            duration = concat_wavs(results, dest)
            self.events.put(("done", (dest, duration, len(chunks))))

        except Exception as exc:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def _poll_events(self) -> None:
        """Разбирает очередь событий из рабочего потока."""
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass

        if self.busy:
            self.root.after(50, self._poll_events)

    def _handle_event(self, kind: str, payload: object) -> None:
        if kind == "download":
            self.progress.configure(value=int(payload))  # type: ignore[arg-type]
        elif kind == "progress":
            self.progress.configure(value=int(payload))  # type: ignore[arg-type]
            self.set_status(f"Синтез: {payload}%")
        elif kind == "status":
            self.set_status(str(payload))
        elif kind == "error":
            self._set_busy(False)
            self.set_status(str(payload), error=True)
        elif kind == "done":
            dest, duration, parts = payload  # type: ignore[misc]
            self.last_audio = dest  # type: ignore[assignment]
            self._set_busy(False)
            self.play_button.configure(state="normal")
            played = self.player.play(self.last_audio)
            self.set_status(
                f"Готово: {duration:.1f} c, {parts} "
                f"{plural_ru(parts, 'фрагмент', 'фрагмента', 'фрагментов')}."
                + ("" if played else " Откройте файл в плеере вручную."),
                success=True,
            )

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.speak_button.configure(state="disabled" if busy else "normal")
        self.voice_box.configure(state="disabled" if busy else "readonly")
        self.speed_box.configure(state="disabled" if busy else "readonly")
        if not busy:
            self.progress.pack_forget()

    # --- Воспроизведение ---

    def stop_playback(self) -> None:
        self.player.stop()
        self.play_button.configure(state="disabled")
        self.set_status("Воспроизведение остановлено.")

    def set_status(self, text: str, *, error: bool = False, success: bool = False) -> None:
        if error:
            color = DANGER
        elif success:
            color = SUCCESS
        else:
            color = TEXT_DIM
        self.status_label.configure(text=text, foreground=color)


def build_window() -> tk.Tk:
    root = tk.Tk()
    TTSApp(root)
    return root


def main() -> None:
    build_window().mainloop()


if __name__ == "__main__":
    main()