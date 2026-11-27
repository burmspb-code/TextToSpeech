"""Графический интерфейс (PyQt6), светлая тема.

Синтез выполняется в отдельном потоке: работа движка занимает секунды,
и главный поток Qt всё это время должен оставаться отзывчивым.
Результаты потока возвращаются в очередь и разбираются через QTimer.
"""
import queue
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
FILE_TYPES = "Текстовые файлы (*.txt *.md *.text);;Все файлы (*)"

# Кодировки для чтения. Русские тексты часто лежат в windows-1251.
ENCODINGS = ("utf-8", "cp1251", "latin-1")

# BOM utf-8 проверяем отдельно: кодировка utf-8-sig декодирует любой
# utf-8 без ошибок, поэтому в общем списке она помечала бы обычный
# файл как имеющий BOM, а при сохранении добавила бы лишние байты.
UTF8_BOM = b"\xef\xbb\xbf"

STYLE_SHEET = f"""
QWidget#central {{ background: {BG}; color: {TEXT};
                   font-family: '{FONT}'; font-size: {FONT_SIZE}pt; }}
QWidget#card {{ background: {SURFACE}; border: 1px solid {BORDER};
                border-radius: 6px; }}
QLabel#Title {{ color: {TEXT}; font-size: 15pt; font-weight: 700; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QPushButton {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
               border-radius: 6px; padding: 8px 14px; }}
QPushButton:hover {{ background: #EAEEF2; }}
QPushButton:disabled {{ background: {BG}; color: #A8B0B8; }}
QPushButton#Accent {{ background: {ACCENT}; color: #FFFFFF;
                      border-color: {ACCENT}; font-weight: 700; padding: 9px 22px; }}
QPushButton#Accent:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Accent:pressed {{ background: {ACCENT_ACTIVE}; }}
QPushButton#Accent:disabled {{ background: #B6C6E4; color: #EEF2F9; }}
QComboBox {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
             border-radius: 6px; padding: 6px 8px; }}
QComboBox:disabled {{ background: {BG}; color: #A8B0B8; }}
QPlainTextEdit {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
                  border-radius: 6px; padding: 14px 16px; font-size: 11pt;
                  selection-background-color: #CCE0FF; }}
QProgressBar {{ border: 1px solid {BORDER}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
"""


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


class TTSApp(QMainWindow):
    """Главное окно приложения."""

    def __init__(self) -> None:
        # QApplication должен существовать до создания любого QWidget.
        self.qapp = QApplication.instance() or QApplication(sys.argv)
        super().__init__()

        self.current_path: Path | None = None
        # Кодировка файла нужна, чтобы сохранить правки в том же формате.
        self.current_encoding: str | None = None
        # Правки пользователя не сохранены на диске.
        self.dirty = False
        # Пока идёт загрузка файла, правки не считаются пользовательскими.
        self._loading = False
        # Ссылка для тестов и внешнего кода.
        self.tts_app = self

        self.setWindowTitle(f"TextToSpeech {__version__}")
        self.resize(860, 620)
        self.setMinimumSize(640, 520)
        self.setStyleSheet(STYLE_SHEET)

        self.engine = PiperEngine()
        self.player = Player()
        self.last_audio: Path | None = None
        self.busy = False
        # Поток докладывает о ходе дела сюда, главный поток забирает
        # через QTimer. Обмен через очередь — безопасный способ передачи
        # данных между потоками.
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll_events)
        self._timer.start()

        self._update_title()
        self.set_status("Готов. Откройте файл или введите текст в поле ниже.")

    # --- Построение интерфейса ---

    def _build(self) -> None:
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._build_header(layout)
        self._build_toolbar(layout)
        self._build_content(layout)
        self._build_controls(layout)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Dim")
        layout.addWidget(self.status_label)

    def _build_header(self, layout: QVBoxLayout) -> None:
        header = QWidget()
        header.setObjectName("card")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 14, 18, 14)

        title = QLabel("TextToSpeech")
        title.setObjectName("Title")
        subtitle = QLabel("Офлайн-синтез речи на движке Piper")
        subtitle.setObjectName("Dim")

        row.addWidget(title)
        row.addSpacing(12)
        row.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(header)

    def _build_toolbar(self, layout: QVBoxLayout) -> None:
        bar = QWidget()
        bar.setObjectName("card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 10, 18, 10)

        open_button = QPushButton("Открыть файл")
        open_button.clicked.connect(self.open_file)

        self.path_label = QLabel("Файл не выбран")
        self.path_label.setObjectName("Dim")

        clear_button = QPushButton("Очистить")
        clear_button.clicked.connect(self.clear_file)

        self.save_button = QPushButton("Сохранить")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_file)

        row.addWidget(open_button)
        row.addSpacing(14)
        row.addWidget(self.path_label, stretch=1)
        row.addWidget(clear_button)
        row.addWidget(self.save_button)
        layout.addWidget(bar)

    def _build_content(self, layout: QVBoxLayout) -> None:
        self.text_area = QPlainTextEdit()
        self.text_area.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_area.setUndoRedoEnabled(True)
        self.text_area.textChanged.connect(self._on_text_modified)
        layout.addWidget(self.text_area, stretch=1)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_file)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_file)

    def _build_controls(self, layout: QVBoxLayout) -> None:
        panel = QWidget()
        panel.setObjectName("card")
        row = QHBoxLayout(panel)
        row.setContentsMargins(18, 12, 18, 12)

        voice_label = QLabel("Голос")
        voice_label.setObjectName("Dim")
        self.voice_box = QComboBox()
        self.voice_box.addItems([v.label for v in CATALOG])
        self.voice_box.setCurrentText(self._label_of(DEFAULT_VOICE_KEY))
        self.voice_box.currentIndexChanged.connect(self._on_voice_changed)

        speed_label = QLabel("Скорость")
        speed_label.setObjectName("Dim")
        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.speed_box.setCurrentText("1.0x")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.stop_button = QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_playback)

        self.speak_button = QPushButton("Озвучить")
        self.speak_button.setObjectName("Accent")
        self.speak_button.clicked.connect(self.on_synthesize)

        row.addWidget(voice_label)
        row.addSpacing(8)
        row.addWidget(self.voice_box)
        row.addSpacing(16)
        row.addWidget(speed_label)
        row.addSpacing(8)
        row.addWidget(self.speed_box)
        row.addStretch(1)
        row.addWidget(self.progress)
        row.addSpacing(16)
        row.addWidget(self.stop_button)
        row.addSpacing(8)
        row.addWidget(self.speak_button)
        layout.addWidget(panel)

    # --- Действия ---

    def open_file(self) -> None:
        """Показывает диалог выбора файла и загружает выбранный."""
        selected, _ = QFileDialog.getOpenFileName(
            self, "Открыть текстовый файл", "", FILE_TYPES
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
        """Подставляет текст в поле, не помечая его как правку пользователя."""
        self._loading = True
        try:
            self.text_area.setPlainText(content)
        finally:
            self._loading = False
        # Курсор в конце: следующая правка дописывается, а не вставляется
        # в начало загруженного текста.
        self.text_area.moveCursor(QTextCursor.MoveOperation.End)

    @property
    def current_text(self) -> str:
        """Актуальный текст из поля — единственный источник истины."""
        return self.text_area.toPlainText()

    # --- Правки и сохранение ---

    def _on_text_modified(self, *_args: object) -> None:
        if self._loading or self.dirty:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.save_button.setEnabled(dirty)
        self._update_title()
        self._refresh_path_label()

    def _update_title(self) -> None:
        if self.current_path:
            mark = " *" if self.dirty else ""
            self.setWindowTitle(f"{self.current_path.name}{mark} — TextToSpeech {__version__}")
        else:
            self.setWindowTitle(f"TextToSpeech {__version__}")

    def _refresh_path_label(self) -> None:
        if self.current_path is None:
            self.path_label.setText("Новый текст")
            return
        parts = [self.current_path.name]
        if self.current_encoding:
            parts.append(self.current_encoding)
        if self.dirty:
            parts.append("изменён")
        self.path_label.setText(" · ".join(parts))

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
        selected, _ = QFileDialog.getSaveFileName(
            self, "Сохранить текст", "", FILE_TYPES, "*.txt"
        )
        return Path(selected) if selected else None

    def _confirm_discard(self, action: str) -> bool:
        """Спрашивает, что делать с несохранёнными правками.

        True — можно продолжать, False — пользователь передумал.
        """
        if not self.dirty:
            return True

        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Несохранённые изменения",
            f"{action}\n\nТекст изменён, изменения не сохранены.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            self,
        )
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
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

    def closeEvent(self, event) -> None:
        """Не даёт закрыть окно с несохранёнными правками."""
        if not self._confirm_discard("Закрыть программу?"):
            event.ignore()
            return
        self.player.stop()
        super().closeEvent(event)

    # --- Голос и скорость ---

    @staticmethod
    def _label_of(key: str) -> str:
        return find_voice(key).label

    @property
    def selected_voice(self) -> Voice:
        return find_voice_by_label(self.voice_box.currentText())

    @property
    def selected_speed(self) -> float:
        return float(self.speed_box.currentText().rstrip("x"))

    def _on_voice_changed(self, *_args: object) -> None:
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
        self.progress.setValue(0)

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

    def _handle_event(self, kind: str, payload: object) -> None:
        if kind == "download":
            self.progress.setValue(int(payload))  # type: ignore[arg-type]
        elif kind == "progress":
            self.progress.setValue(int(payload))  # type: ignore[arg-type]
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
            self.stop_button.setEnabled(True)
            played = self.player.play(self.last_audio)
            self.set_status(
                f"Готово: {duration:.1f} c, {parts} "
                f"{plural_ru(parts, 'фрагмент', 'фрагмента', 'фрагментов')}."
                + ("" if played else " Откройте файл в плеере вручную."),
                success=True,
            )

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.speak_button.setEnabled(not busy)
        self.voice_box.setEnabled(not busy)
        self.speed_box.setEnabled(not busy)
        self.progress.setVisible(busy)

    # --- Воспроизведение ---

    def stop_playback(self) -> None:
        self.player.stop()
        self.stop_button.setEnabled(False)
        self.set_status("Воспроизведение остановлено.")

    def set_status(self, text: str, *, error: bool = False, success: bool = False) -> None:
        if error:
            color = DANGER
        elif success:
            color = SUCCESS
        else:
            color = TEXT_DIM
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def center_on_screen(self) -> None:
        """Ставит окно по центру доступной области экрана."""
        screen = self.qapp.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())


def build_window() -> TTSApp:
    """Создаёт приложение, центрирует и показывает главное окно."""
    window = TTSApp()
    window.show()
    window.center_on_screen()
    return window


def main() -> None:
    window = build_window()
    window.qapp.exec()


if __name__ == "__main__":
    main()
