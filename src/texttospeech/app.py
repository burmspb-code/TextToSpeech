"""Графический интерфейс (PyQt6), светлая тема.

Синтез выполняется в отдельном потоке: работа движка занимает секунды,
и главный поток Qt всё это время должен оставаться отзывчивым.
Результаты потока возвращаются в очередь и разбираются через QTimer.
"""
import math
import queue
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import (
    QEvent,
    QLineF,
    QPoint,
    QRect,
    QSettings,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QShortcut,
    QTextCursor,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from . import __version__
from .audio import concat_wavs
from .engines import PiperEngine, SileroEngine, split_text
from .logging_setup import configure_logging
from .paths import OUTPUT_DIR
from .voices import (
    DEFAULT_QUALITY_BY_ENGINE,
    DEFAULT_VOICE_BY_ENGINE,
    Voice,
    find_voice,
    find_voice_by_label,
    voice_size_mb,
    voices_for_quality,
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
WAVE_PURPLE = "#8A5CFF"  # вторая волна индикатора воспроизведения
WAVE_GREEN = "#22C55E"   # третья волна индикатора воспроизведения
WAVE_TRACK = "#D9F2EE"   # фон дорожки: светло-бирюзовый
DANGER = "#CF222E"
SUCCESS = "#1A7F37"

# Иконка приложения лежит рядом с кодом и попадает в пакет.
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "tts.png"
APP_ICON_SIZE = 28

FONT = "Segoe UI"
FONT_SIZE = 10

# Файлы, которые имеет смысл открывать.
FILE_TYPES = "Текстовые файлы (*.txt *.md *.text);;Все файлы (*)"

# Кнопки собственной шапки окна (системная рамка отключена).
TITLE_MINIMIZE = "−"
TITLE_MAXIMIZE = "□"
TITLE_RESTORE = "❐"
TITLE_CLOSE = "×"
TITLE_RESIZE_MARGIN = 8

# Скругление окна и отступ содержимого от его края.
WINDOW_RADIUS = 10
WINDOW_INSET = 18

# Скорости озвучивания; меню настроек использует те же подписи.
SPEEDS = ("0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x")
DEFAULT_SPEED = "1.0x"

# Оба движка офлайн. Silero можно выбрать, если установлен extra `silero`.
ENGINE_LABELS = {"piper": "Piper", "silero": "Silero"}
ENGINE_KEYS = tuple(ENGINE_LABELS)
DEFAULT_ENGINE = "silero"

# Кодировки для чтения. Русские тексты часто лежат в windows-1251.
ENCODINGS = ("utf-8", "cp1251", "latin-1")

# BOM utf-8 проверяем отдельно: кодировка utf-8-sig декодирует любой
# utf-8 без ошибок, поэтому в общем списке она помечала бы обычный
# файл как имеющий BOM, а при сохранении добавила бы лишние байты.
UTF8_BOM = b"\xef\xbb\xbf"

STYLE_SHEET = f"""
QMainWindow {{ background: transparent; }}
QWidget#central {{ background: {BG}; color: {TEXT};
                   border: 1px solid {BORDER}; border-top: 0;
                   border-bottom-left-radius: {WINDOW_RADIUS}px;
                   border-bottom-right-radius: {WINDOW_RADIUS}px;
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
QPushButton#Dropdown {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
                        border-radius: 6px; padding: 6px 10px; }}
QPushButton#Dropdown:hover {{ background: #EAEEF2; border-color: #A8B0B8; }}
QPushButton#Dropdown:pressed {{ background: #DDE4EB; }}
QPushButton#Dropdown:disabled {{ background: {BG}; color: #A8B0B8; }}
QPushButton#folderButton {{ text-align: left; padding: 6px 10px; }}
QMenuBar {{ background: {SURFACE}; color: {TEXT};
            border: 1px solid {BORDER}; border-bottom: 0;
            border-top-left-radius: {WINDOW_RADIUS}px;
            border-top-right-radius: {WINDOW_RADIUS}px; }}
QMenuBar::item {{ padding: 6px 12px; margin: 3px 2px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: #EAEEF2; }}
QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
         border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: #CCE0FF; }}
QMenu::item:checked {{ font-weight: 700; }}
QWidget#titleCorner {{ background: transparent;
                       border-top-right-radius: {WINDOW_RADIUS}px; }}
QWidget#titleDrag {{ background: transparent; }}
QPushButton#TitleButton, QPushButton#CloseButton {{ background: transparent;
                           color: {TEXT_DIM}; border: 0; border-radius: 4px;
                           padding: 5px 11px; font-size: 12pt; }}
QPushButton#TitleButton:hover {{ background: #EAEEF2; color: {TEXT}; }}
QPushButton#CloseButton:hover {{ background: #E81123; color: #FFFFFF; }}
QWidget#settingsPanel {{ background: {SURFACE}; }}
QPlainTextEdit {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
                  border-radius: 6px; padding: 14px 16px; font-size: 11pt;
                  selection-background-color: #CCE0FF; }}
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


def _chevron_icon() -> QIcon:
    """Аккуратный шеврон вместо системной стрелки выпадающего списка."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(TEXT_DIM))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QLineF(4.0, 6.5, 8.0, 10.0))
    painter.drawLine(QLineF(8.0, 10.0, 12.0, 6.5))
    painter.end()
    return QIcon(pixmap)


class SoundWaveProgress(QWidget):
    """Волна в шапке: показывает позицию воспроизведения готового WAV."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SoundWave")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setFixedHeight(28)

        self._value = 0
        self._phase = 0.0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance)

    def setRange(self, minimum: int, maximum: int) -> None:
        """Оставлено для совместимости с QProgressBar."""
        self._minimum = minimum
        self._maximum = maximum

    def setValue(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        self.update()

    def value(self) -> int:
        return self._value

    def isTextVisible(self) -> bool:
        return False

    def setTextVisible(self, _visible: bool) -> None:
        """Текст не рисуется: прогресс виден по длине волны."""

    def setPlaying(self, playing: bool) -> None:
        """Анимация идёт только во время воспроизведения."""
        self._playing = playing
        if playing:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def isPlaying(self) -> bool:
        return self._playing

    def _advance(self) -> None:
        self._phase = (self._phase + 0.22) % math.tau
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 3, 0, -3)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(WAVE_TRACK))
        painter.drawRoundedRect(rect, 8, 8)

        if self._value:
            progress_width = rect.width() * self._value // 100
            painter.save()
            painter.setClipRect(0, 0, progress_width, self.height())
            # Три волны разной амплитуды и фазы растут слева направо.
            self._draw_wave(
                painter, rect, QColor(ACCENT), alpha=1.0,
                amplitude=6.5, phase=0.0,
            )
            self._draw_wave(
                painter, rect, QColor(WAVE_PURPLE), alpha=1.0,
                amplitude=5.0, phase=0.8,
            )
            self._draw_wave(
                painter, rect, QColor(WAVE_GREEN), alpha=1.0,
                amplitude=3.5, phase=1.6,
            )
            painter.restore()

    def _draw_wave(
        self,
        painter: QPainter,
        rect,
        color: QColor,
        *,
        alpha: float,
        amplitude: float,
        phase: float,
    ) -> None:
        wave_color = QColor(color)
        wave_color.setAlphaF(alpha)
        pen = QPen(wave_color)
        pen.setWidthF(2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        middle = rect.center().y()
        step = max(4, rect.width() // 90)
        path = QPainterPath()
        for index, x in enumerate(range(0, rect.width() + step, step)):
            envelope = 0.45 + 0.55 * math.sin(
                x / max(rect.width(), 1) * math.pi
            )
            offset = (
                math.sin(x / 26 + self._phase + phase) * amplitude
                + math.sin(x / 11 - self._phase * 1.7 + phase) * 2.0
            ) * envelope
            if index == 0:
                path.moveTo(x, middle + offset)
            else:
                path.lineTo(x, middle + offset)
        painter.drawPath(path)


class ProgressButton(QPushButton):
    """Кнопка «Озвучить», чей фон плавно заполняется слева направо.

    События из потока синтеза приходят пачками и могут разобраться за один
    тик таймера, поэтому заливка не прыгает, а дорисовывается по шагам.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._target = 0
        self._progress = 0
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._advance)

    def setProgress(self, value: int) -> None:
        percent = max(0, min(100, int(value)))
        if percent == self._target:
            return
        self._target = percent
        if percent <= self._progress:
            # Сброс или откат назад показываем сразу.
            self._timer.stop()
            self._progress = percent
            self._apply_fill()
        else:
            self._timer.start()

    def progress(self) -> int:
        """Текущая (отрисованная) степень заполнения."""
        return self._progress

    def targetProgress(self) -> int:
        """Последнее значение, полученное от потока синтеза."""
        return self._target

    def _advance(self) -> None:
        if self._progress >= self._target:
            self._timer.stop()
            return
        step = max(1, (self._target - self._progress + 9) // 10)
        self._progress = min(self._target, self._progress + step)
        self._apply_fill()
        if self._progress == self._target:
            self._timer.stop()

    def _apply_fill(self) -> None:
        if self._progress == 0:
            # Пустая заливка: обычный стиль кнопки с hover/pressed.
            self.setStyleSheet("")
            return

        filled = self._progress / 100
        after = min(1.0, filled + 0.001)
        self.setStyleSheet(
            "QPushButton { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {ACCENT_ACTIVE}, stop:{filled:.4f} {ACCENT_ACTIVE}, "
            f"stop:{after:.4f} {ACCENT}, stop:1 {ACCENT}); }}"
        )


class DropdownButton(QPushButton):
    """Кнопка с меню вместо системного QComboBox.

    Выглядит как современный селектор: выбранное значение слева, шеврон
    справа, а список открывается отдельным меню с отметкой текущего пункта.
    """

    currentTextChanged = pyqtSignal(str)

    def __init__(
        self, items: list[str], current: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Dropdown")
        self._current = current
        self.setIcon(_chevron_icon())
        self.setIconSize(QSize(16, 16))
        self.setText(current)

        self._menu = QMenu(self)
        self._actions: dict[str, QAction] = {}
        for item in items:
            action = self._menu.addAction(item)
            action.setCheckable(True)
            action.setChecked(item == current)
            action.triggered.connect(
                lambda _checked=False, value=item: self.setCurrentText(value)
            )
            self._actions[item] = action

    def currentText(self) -> str:
        return self._current

    def setItems(self, items: list[str], current: str | None = None) -> None:
        """Заменяет пункты меню (нужно при смене уровня качества)."""
        self._menu.clear()
        self._actions.clear()
        for item in items:
            action = self._menu.addAction(item)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=item: self.setCurrentText(value)
            )
            self._actions[item] = action

        chosen = current if current in items else (items[0] if items else "")
        for item, action in self._actions.items():
            action.setChecked(item == chosen)
        self._current = chosen
        self.setText(chosen)
        if chosen:
            self.currentTextChanged.emit(chosen)

    def setCurrentText(self, value: str) -> None:
        action = self._actions.get(value)
        if action is None or value == self._current:
            return
        for other in self._actions.values():
            other.setChecked(False)
        action.setChecked(True)
        self._current = value
        self.setText(value)
        self.currentTextChanged.emit(value)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Меню внутри QWidgetAction не должно закрывать родительское меню.
            event.accept()
            self._menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Enter, Qt.Key.Key_Return):
            self._menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        # В обычном стиле иконка слева; зеркалим направление только
        # отрисовки, чтобы шеврон оказался справа от подписи.
        option.direction = Qt.LayoutDirection.RightToLeft
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)


def saved_output_dir() -> Path:
    """Папка для файлов из настроек, по умолчанию ``output/`` проекта."""
    settings = QSettings("TextToSpeech", "TextToSpeech")
    saved = settings.value("outputDir", "", type=str)
    return Path(saved) if saved else OUTPUT_DIR


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
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(860, 620)
        self.setMinimumSize(640, 520)
        self.setStyleSheet(STYLE_SHEET)
        # Своя шапка вместо системной: кнопки живут в строке меню,
        # окно перетаскивается за её пустое место.
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_origin: QPoint | None = None
        self._resize_origin: tuple[int, QPoint, QRect] | None = None
        self._title_drag: QWidget | None = None

        self.engines: dict[str, object] = {
            "piper": PiperEngine(),
            "silero": SileroEngine(),
        }
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self._on_playback_position)
        self.media_player.durationChanged.connect(self._on_playback_duration)
        self.media_player.playbackStateChanged.connect(self._on_playback_state)
        self.media_player.mediaStatusChanged.connect(self._on_media_status)
        self.media_player.errorOccurred.connect(self._on_playback_error)
        self._playback_duration_ms = 0
        self.last_audio: Path | None = None
        self.busy = False
        # Поток докладывает о ходе дела сюда, главный поток забирает
        # через QTimer. Обмен через очередь — безопасный способ передачи
        # данных между потоками.
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._qsettings = QSettings("TextToSpeech", "TextToSpeech")
        self.output_dir = saved_output_dir()

        # Каждый движок помнит свои качество, голос и скорость: при
        # переключении выбор пользователя не теряется.
        self._settings_by_engine: dict[str, dict[str, str]] = {
            key: {
                "quality": DEFAULT_QUALITY_BY_ENGINE[key],
                "voice": DEFAULT_VOICE_BY_ENGINE[key],
                "speed": DEFAULT_SPEED,
            }
            for key in ENGINE_KEYS
        }
        self._current_engine = DEFAULT_ENGINE

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
        central.installEventFilter(self)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(WINDOW_INSET, WINDOW_INSET, WINDOW_INSET, WINDOW_INSET)
        layout.setSpacing(10)

        self._build_menu()
        self._build_header(layout)
        self._build_toolbar(layout)
        self._build_content(layout)
        self._build_controls(layout)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Dim")
        layout.addWidget(self.status_label)

    def _build_menu(self) -> None:
        """Меню приложения: настройки синтеза и сведения о программе."""
        menu_bar = self.menuBar()
        self.settings_menu = menu_bar.addMenu("Настройки")
        # «О программе» — пункт верхнего уровня: по нажатию сразу открывается
        # диалог, без дополнительного вложенного меню.
        self.about_action = menu_bar.addAction("О программе")
        self.about_action.triggered.connect(self.show_about)

        self._build_title_buttons(menu_bar)

        panel = QWidget(self.settings_menu)
        panel.setObjectName("settingsPanel")
        form = QFormLayout(panel)
        form.setContentsMargins(16, 12, 16, 12)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        engine = self._current_engine
        saved = self._settings_by_engine[engine]
        self.engine_box = DropdownButton(
            [ENGINE_LABELS[key] for key in ENGINE_KEYS],
            ENGINE_LABELS[engine],
        )
        self.voice_box = DropdownButton(
            [v.label for v in voices_for_quality(saved["quality"], engine)],
            self._label_of(saved["voice"]),
        )
        self.speed_box = DropdownButton(list(SPEEDS), saved["speed"])
        self._settings_panel = panel  # QWidgetAction не владеет виджетом.

        form.addRow("Движок:", self.engine_box)
        form.addRow("Голос:", self.voice_box)
        form.addRow("Скорость:", self.speed_box)
        self.output_button = QPushButton(str(self.output_dir))
        self.output_button.setObjectName("folderButton")
        self.output_button.setToolTip("Нажмите, чтобы выбрать другую папку")
        self.output_button.clicked.connect(self._choose_output_dir)
        form.addRow("Папка файлов:", self.output_button)

        settings_action = QWidgetAction(self.settings_menu)
        settings_action.setDefaultWidget(panel)
        self.settings_menu.addAction(settings_action)

        self.engine_box.currentTextChanged.connect(self._on_engine_changed)
        self.voice_box.currentTextChanged.connect(self._on_voice_changed)
        self.speed_box.currentTextChanged.connect(self._on_speed_changed)

    def _build_title_buttons(self, menu_bar: QMenuBar) -> None:
        """Свои кнопки окна в правой части строки меню."""
        corner = QWidget(menu_bar)
        corner.setObjectName("titleCorner")
        corner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row = QHBoxLayout(corner)
        row.setContentsMargins(6, 4, 10, 6)
        row.setSpacing(0)

        drag = QWidget(corner)
        drag.setObjectName("titleDrag")
        drag.setFixedWidth(48)
        row.addWidget(drag)
        self._title_drag = drag

        self.min_button = QPushButton(TITLE_MINIMIZE)
        self.min_button.setObjectName("TitleButton")
        self.min_button.setToolTip("Свернуть")
        self.min_button.clicked.connect(self.showMinimized)

        self.max_button = QPushButton(TITLE_MAXIMIZE)
        self.max_button.setObjectName("TitleButton")
        self.max_button.setToolTip("Развернуть")
        self.max_button.clicked.connect(self._toggle_maximized)

        self.close_button = QPushButton(TITLE_CLOSE)
        self.close_button.setObjectName("CloseButton")
        self.close_button.setToolTip("Закрыть")
        self.close_button.clicked.connect(self.close)

        for button in (self.min_button, self.max_button, self.close_button):
            row.addWidget(button)

        menu_bar.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        menu_bar.installEventFilter(self)
        drag.installEventFilter(self)

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.max_button.setText(TITLE_MAXIMIZE)
            self.max_button.setToolTip("Развернуть")
        else:
            self.showMaximized()
            self.max_button.setText(TITLE_RESTORE)
            self.max_button.setToolTip("Восстановить")

    def _build_header(self, layout: QVBoxLayout) -> None:
        """Шапка: иконка и название. Сведения о движке — в «О программе»."""
        header = QWidget()
        header.setObjectName("card")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(10)

        icon = QLabel()
        icon.setObjectName("AppIcon")
        pixmap = QPixmap(str(APP_ICON_PATH))
        if not pixmap.isNull():
            icon.setPixmap(
                pixmap.scaled(
                    APP_ICON_SIZE,
                    APP_ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        row.addWidget(icon)

        title = QLabel("TextToSpeech")
        title.setObjectName("Title")
        row.addWidget(title)

        self.progress = SoundWaveProgress()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        row.addWidget(self.progress, 1)
        layout.addWidget(header)

    def _build_toolbar(self, layout: QVBoxLayout) -> None:
        bar = QWidget()
        bar.setObjectName("card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 10, 18, 10)

        open_button = QPushButton("Открыть файл")
        open_button.clicked.connect(self.open_file)

        paste_button = QPushButton("Вставить текст из буфера")
        paste_button.clicked.connect(self.paste_from_clipboard)

        self.path_label = QLabel("Файл не выбран")
        self.path_label.setObjectName("Dim")

        clear_button = QPushButton("Очистить")
        clear_button.clicked.connect(self.clear_file)

        self.save_button = QPushButton("Сохранить")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_file)

        row.addWidget(open_button)
        row.addSpacing(10)
        row.addWidget(paste_button)
        row.addSpacing(10)
        row.addWidget(self.path_label, stretch=1)
        row.addWidget(clear_button)
        row.addSpacing(8)
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

        self.stop_button = QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_playback)

        self.speak_button = ProgressButton("Озвучить")
        self.speak_button.setObjectName("Accent")
        self.speak_button.clicked.connect(self.on_synthesize)

        row.addStretch(1)
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

    def paste_from_clipboard(self) -> None:
        """Вставляет текст из буфера в позицию курсора."""
        text = self.qapp.clipboard().text()
        if not text:
            self.set_status("Буфер обмена пуст.", error=True)
            return

        cursor = self.text_area.textCursor()
        cursor.insertText(text)
        self.text_area.setTextCursor(cursor)
        self.text_area.setFocus()
        count = len(text)
        self.set_status(
            f"Вставлено из буфера: {count} "
            f"{plural_ru(count, 'символ', 'символа', 'символов')}.",
            success=True,
        )

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

        # Стандартные подписи кнопок зависят от локали Qt и часто остаются
        # английскими, поэтому задаём русские тексты явно.
        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Несохранённые изменения",
            f"{action}\n\nТекст изменён, изменения не сохранены.",
            QMessageBox.StandardButton.NoButton,
            self,
        )
        save_button = box.addButton(
            "Сохранить", QMessageBox.ButtonRole.AcceptRole
        )
        save_button.setObjectName("SaveButton")
        discard_button = box.addButton(
            "Не сохранять", QMessageBox.ButtonRole.DestructiveRole
        )
        discard_button.setObjectName("DiscardButton")
        cancel_button = box.addButton(
            "Отмена", QMessageBox.ButtonRole.RejectRole
        )
        cancel_button.setObjectName("CancelButton")
        box.setDefaultButton(save_button)

        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_button:
            return False
        if clicked is save_button:
            self.save_file()
            return not self.dirty
        return True

    def clear_file(self) -> None:
        if not self._confirm_discard("Очистить поле?"):
            return

        self._stop_audio()
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
        self._stop_audio()
        super().closeEvent(event)

    # --- Своя рамка окна ---

    def _apply_window_mask(self) -> None:
        """Реально отсекает углы, а не только рисует их прозрачными."""
        path = QPainterPath()
        path.addRoundedRect(
            0, 0, self.width(), self.height(), WINDOW_RADIUS, WINDOW_RADIUS
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_window_mask()

    def _resize_edge(self, pos: QPoint) -> Qt.Edge:
        """Определяет, за какой край окна тянет пользователь."""
        edge = Qt.Edge(0)
        if pos.x() < TITLE_RESIZE_MARGIN:
            edge |= Qt.Edge.LeftEdge
        elif pos.x() > self.width() - TITLE_RESIZE_MARGIN:
            edge |= Qt.Edge.RightEdge
        if pos.y() < TITLE_RESIZE_MARGIN:
            edge |= Qt.Edge.TopEdge
        elif pos.y() > self.height() - TITLE_RESIZE_MARGIN:
            edge |= Qt.Edge.BottomEdge
        return edge

    def eventFilter(self, watched, event):
        """Перетаскивание и изменение размера вместо системной рамки."""
        if isinstance(watched, QMenuBar):
            if event.type() == QEvent.Type.MouseButtonPress:
                # Клик по пункту меню должен открывать меню, а не двигать окно.
                if self.menuBar().actionAt(event.position().toPoint()) is not None:
                    return super().eventFilter(watched, event)
                self._drag_origin = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_origin is not None:
                if not self.isMaximized():
                    self.move(event.globalPosition().toPoint() - self._drag_origin)
                return True
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and self._drag_origin is not None
            ):
                # Нажатие было по пустому месту — это было перетаскивание.
                self._drag_origin = None
                return True

        if self._title_drag is not None and watched is self._title_drag:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._drag_origin = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_origin is not None:
                if not self.isMaximized():
                    self.move(event.globalPosition().toPoint() - self._drag_origin)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_origin = None
                return True

        if watched is self.centralWidget():
            if event.type() == QEvent.Type.MouseButtonPress:
                edge = self._resize_edge(event.position().toPoint())
                if edge:
                    self._resize_origin = (
                        int(edge),
                        event.globalPosition().toPoint(),
                        self.geometry(),
                    )
                    return True
            if event.type() == QEvent.Type.MouseMove and self._resize_origin is not None:
                edge_value, origin, geometry = self._resize_origin
                edge = Qt.Edge(edge_value)
                delta = event.globalPosition().toPoint() - origin
                if edge & Qt.Edge.LeftEdge:
                    geometry.setLeft(geometry.left() + delta.x())
                if edge & Qt.Edge.RightEdge:
                    geometry.setRight(geometry.right() + delta.x())
                if edge & Qt.Edge.TopEdge:
                    geometry.setTop(geometry.top() + delta.y())
                if edge & Qt.Edge.BottomEdge:
                    geometry.setBottom(geometry.bottom() + delta.y())
                self.setGeometry(geometry)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._resize_origin = None
                return True

        return super().eventFilter(watched, event)

    # --- Голос и скорость ---

    @staticmethod
    def _label_of(key: str) -> str:
        return find_voice(key).label

    @property
    def engine(self) -> object:
        """Активный движок синтеза."""
        return self.engines[self.selected_engine_key]

    @property
    def selected_engine_key(self) -> str:
        for key, label in ENGINE_LABELS.items():
            if label == self.engine_box.currentText():
                return key
        return DEFAULT_ENGINE

    @property
    def selected_quality(self) -> str:
        """Качество зафиксировано: Silero 48 кГц, Piper medium."""
        return DEFAULT_QUALITY_BY_ENGINE[self.selected_engine_key]

    @property
    def selected_voice(self) -> Voice:
        return find_voice_by_label(
            self.voice_box.currentText(),
            self.selected_quality,
            self.selected_engine_key,
        )

    @property
    def selected_speed(self) -> float:
        return float(self.speed_box.currentText().rstrip("x"))

    def _remember_settings(self, engine: str | None = None) -> None:
        """Запоминает текущие голос и скорость за движком."""
        engine = engine or self._current_engine
        quality = DEFAULT_QUALITY_BY_ENGINE[engine]
        voice = find_voice_by_label(self.voice_box.currentText(), quality, engine)
        self._settings_by_engine[engine] = {
            "quality": quality,
            "voice": voice.key,
            "speed": self.speed_box.currentText(),
        }

    def _restore_settings(self, engine: str) -> None:
        """Возвращает настройки, которые были у движка до переключения."""
        self._current_engine = engine
        saved = self._settings_by_engine[engine]
        quality = DEFAULT_QUALITY_BY_ENGINE[engine]

        voices = voices_for_quality(quality, engine)
        labels = [v.label for v in voices]
        try:
            voice = find_voice(saved["voice"])
        except ValueError:
            voice = None
        voice_label = (
            voice.label
            if voice is not None
            and voice.engine == engine
            and voice.quality == quality
            and voice.label in labels
            else (labels[0] if labels else "")
        )
        speed = saved["speed"] if saved["speed"] in SPEEDS else DEFAULT_SPEED

        # Программная подстановка значений не должна вызывать обработчики
        # и перезаписать сохранённые настройки промежуточными значениями.
        with (
            QSignalBlocker(self.voice_box),
            QSignalBlocker(self.speed_box),
        ):
            self.voice_box.setItems(labels, voice_label)
            self.speed_box.setCurrentText(speed)

    def _on_engine_changed(self, *_args: object) -> None:
        """Смена движка восстанавливает его прошлые качество, голос и скорость."""
        engine = self.selected_engine_key
        if engine == self._current_engine:
            return
        self._remember_settings(self._current_engine)
        self._restore_settings(engine)
        if self.engine.is_available():
            self.set_status(
                f"Движок: {ENGINE_LABELS[engine]}. Голос {self.selected_voice.title}."
            )
        else:
            self.set_status(
                f"Движок {ENGINE_LABELS[engine]} не установлен. "
                f"Установите: poetry install -E {engine}.",
                error=True,
            )

    def _on_voice_changed(self, *_args: object) -> None:
        self._remember_settings()
        voice = self.selected_voice
        if voice.is_downloaded:
            self.set_status(f"Голос {voice.title} уже загружен.")
        else:
            mb = voice_size_mb(voice)
            self.set_status(f"Голос {voice.title} будет скачан при синтезе (~{mb:.0f} МБ).")

    def _on_speed_changed(self, *_args: object) -> None:
        self._remember_settings()
        self.set_status(f"Скорость: {self.speed_box.currentText()}")

    def _choose_output_dir(self) -> None:
        """Выбрать папку для готовых WAV, фрагментов и журнала."""
        selected = QFileDialog.getExistingDirectory(
            self, "Папка для звуковых файлов", str(self.output_dir)
        )
        if not selected:
            return
        path = Path(selected)
        self.output_dir = path
        self.output_button.setText(str(path))
        self._qsettings.setValue("outputDir", str(path))
        self._qsettings.sync()
        configure_logging(path / "texttospeech.log")
        self.set_status(f"Папка для файлов: {path}")

    # --- Синтез ---

    def on_synthesize(self) -> None:
        """Запускает синтез в фоновом потоке."""
        if self.busy:
            return
        if not self.current_text.strip():
            self.set_status("Сначала откройте файл с текстом.", error=True)
            return
        engine = self.engine
        if not engine.is_available():
            self.set_status(
                f"Движок {ENGINE_LABELS[self.selected_engine_key]} не установлен.",
                error=True,
            )
            return

        voice = self.selected_voice
        speed = self.selected_speed

        self._set_busy(True)
        self._stop_audio()
        self.speak_button.setProgress(0)

        if voice.is_downloaded:
            self.set_status(f"Синтез голосом {voice.title}...")
        else:
            mb = voice_size_mb(voice)
            self.set_status(f"Скачиваю модель {engine.name} (~{mb:.0f} МБ)...")

        self._worker = threading.Thread(
            target=self._synthesize_worker,
            args=(self.current_text, voice, speed, engine),
            daemon=True,
        )
        self._worker.start()

    def _synthesize_worker(
        self, text: str, voice: Voice, speed: float, engine: object
    ) -> None:
        """Синтез в отдельном потоке. Всё общение с UI — через очередь.

        Ход синтеза уходит в «Озвучить» как заливка фона; волна в шапке
        остаётся индикатором воспроизведения и тут не участвует.
        """
        try:
            # Загрузка занимает первые 40%, синтез — следующие 55%,
            # сборка итогового WAV — последние 5%.
            download_span = 0
            if not voice.is_downloaded:
                self.events.put(("status", f"Скачиваю модель {engine.name}..."))
                engine.prepare(voice)
                download_span = 40

            chunks = split_text(text)
            if not chunks:
                self.events.put(("error", "В файле нет текста для синтеза."))
                return

            parts_dir = self.output_dir / "parts"
            parts_dir.mkdir(parents=True, exist_ok=True)

            synthesis_span = 55 if download_span else 95
            results = []
            for index, chunk in enumerate(chunks, start=1):
                part = parts_dir / f"part_{index:04d}.wav"
                results.append(
                    engine.synthesize(chunk, voice, part, speed=speed).path
                )
                percent = download_span + index * synthesis_span // len(chunks)
                self.events.put(("synthesis_progress", min(percent, 99)))

            self.events.put(("status", "Объединяю фрагменты..."))
            dest = self.output_dir / f"{voice.key}_{speed:g}x.wav"
            duration = concat_wavs(results, dest)
            # Фрагменты нужны только до успешной склейки.
            for part in results:
                part.unlink(missing_ok=True)
            try:
                parts_dir.rmdir()
            except OSError:
                pass  # в папке остались чужие файлы — трогать не будем
            self.events.put(("synthesis_progress", 100))
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
        if kind == "synthesis_progress":
            self.speak_button.setProgress(int(payload))  # type: ignore[arg-type]
        elif kind == "status":
            self.set_status(str(payload))
        elif kind == "error":
            self._set_busy(False)
            self.speak_button.setProgress(0)
            self.set_status(str(payload), error=True)
        elif kind == "done":
            dest, duration, parts = payload  # type: ignore[misc]
            self.last_audio = dest  # type: ignore[assignment]
            self._set_busy(False)
            played = self._play_audio(self.last_audio)
            self.set_status(
                f"Готово: {duration:.1f} c, {parts} "
                f"{plural_ru(parts, 'фрагмент', 'фрагмента', 'фрагментов')}."
                + ("" if played else " Откройте файл в плеере вручную."),
                success=True,
            )

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.speak_button.setEnabled(not busy)
        self.engine_box.setEnabled(not busy)
        self.voice_box.setEnabled(not busy)
        self.speed_box.setEnabled(not busy)

    # --- Воспроизведение ---

    def _play_audio(self, path: Path) -> bool:
        """Запускает WAV и включает волну как индикатор позиции."""
        if not path.exists():
            return False
        self.media_player.setSource(QUrl.fromLocalFile(str(path)))
        self.media_player.play()
        self._playback_duration_ms = self.media_player.duration()
        self.progress.setValue(0)
        self.progress.setPlaying(True)
        self.stop_button.setEnabled(True)
        return True

    def _stop_audio(self) -> None:
        self.media_player.stop()
        self._reset_playback_ui()

    def _reset_playback_ui(self) -> None:
        self.progress.setPlaying(False)
        self.progress.setValue(0)
        self.stop_button.setEnabled(False)

    def _finish_playback(self) -> None:
        """Естественный конец дорожки: волна остаётся заполненной."""
        self.progress.setPlaying(False)
        self.progress.setValue(100)
        self.stop_button.setEnabled(False)
        self.set_status("Воспроизведение завершено.")

    def _at_end_of_media(self) -> bool:
        """Конец файла: Qt часто шлёт StoppedState ещё до EndOfMedia."""
        if self.media_player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
            return True
        duration = self._playback_duration_ms
        return duration > 0 and self.media_player.position() >= duration - 50

    def _on_playback_position(self, position_ms: int) -> None:
        if self._playback_duration_ms <= 0:
            return
        percent = min(100, position_ms * 100 // self._playback_duration_ms)
        self.progress.setValue(percent)

    def _on_playback_duration(self, duration_ms: int) -> None:
        self._playback_duration_ms = max(0, duration_ms)

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        if state != QMediaPlayer.PlaybackState.StoppedState:
            return
        if self._at_end_of_media():
            self._finish_playback()
        else:
            # Остановил пользователь или сменился источник — обнуляем волну,
            # но не дёргаем player.stop() повторно, чтобы не зациклиться.
            self._reset_playback_ui()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if (
            status == QMediaPlayer.MediaStatus.EndOfMedia
            and self._at_end_of_media()
        ):
            self._finish_playback()

    def _on_playback_error(
        self, error: QMediaPlayer.Error, message: str
    ) -> None:
        self._reset_playback_ui()
        errors = {
            QMediaPlayer.Error.FormatError: "Неподдерживаемый формат аудио.",
            QMediaPlayer.Error.NetworkError: "Ошибка сети при воспроизведении.",
            QMediaPlayer.Error.ResourceError: "Аудиофайл недоступен.",
            QMediaPlayer.Error.AccessDeniedError: "Нет доступа к аудиофайлу.",
        }
        detail = errors.get(error, "Не удалось воспроизвести аудио.")
        self.set_status(f"{detail} {message}".strip(), error=True)

    def stop_playback(self) -> None:
        self._stop_audio()
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

    @staticmethod
    def about_text() -> str:
        """Текст окна «О программе»: движок и основные приёмы работы."""
        return (
            f"TextToSpeech {__version__}\n\n"
            "Оба движка работают офлайн:\n"
            "• Piper — ONNX Runtime, espeak-ng превращает буквы в фонемы.\n"
            "• Silero — PyTorch, multilingual VITS (без espeak-ng).\n\n"
            "Основные моменты:\n"
            "• «Открыть файл» (Ctrl+O) или ввод текста прямо в окне.\n"
            "• «Вставить текст из буфера» — вставка в позицию курсора.\n"
            "• Меню «Настройки» — движок, голос, скорость и папка файлов.\n"
            "• «Озвучить» работает в фоне, окно остаётся отзывчивым.\n"
            "• «Сохранить» (Ctrl+S) хранит исходную кодировку файла.\n"
            "• Готовый WAV: выбранная папка (по умолчанию output/ в проекте).\n\n"
            "Доступны только русские голоса. У Piper — только medium (~60 МБ), "
            "у Silero качество зафиксировано на 48 кГц. Модели скачиваются "
            "при первом использовании, дальше синтез работает без сети."
        )

    def show_about(self) -> None:
        """Своё окно «О программе» с рабочей кнопкой OK."""
        dialog = QDialog(self)
        dialog.setWindowTitle("О программе")
        dialog.setMinimumWidth(520)

        layout = QVBoxLayout(dialog)
        text = QLabel(self.about_text())
        text.setWordWrap(True)
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(text)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(dialog.accept)
        buttons.addWidget(ok_button)
        layout.addLayout(buttons)

        dialog.exec()

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
    configure_logging(saved_output_dir() / "texttospeech.log")
    window = build_window()
    window.qapp.exec()


if __name__ == "__main__":
    main()
