"""Smoke-тесты интерфейса на PyQt6."""
import queue
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QWidgetAction,
)

from texttospeech.app import (
    APP_ICON_PATH,
    APP_ICON_SIZE,
    DEFAULT_ENGINE,
    OUTPUT_DIR,
    STYLE_SHEET,
    TITLE_CLOSE,
    TITLE_MAXIMIZE,
    TITLE_MINIMIZE,
    WAVE_GREEN,
    WAVE_PURPLE,
    WAVE_TRACK,
    WINDOW_INSET,
    WINDOW_RADIUS,
    DropdownButton,
    ProgressButton,
    SoundWaveProgress,
    TTSApp,
    build_window,
    plural_ru,
    read_text_file,
    saved_output_dir,
)
from texttospeech.voices import (
    CATALOG,
    DEFAULT_SILERO_VOICE_KEY,
    Voice,
    voices_for_quality,
)


def settle_progress(button: ProgressButton) -> None:
    """Прокрутить таймер плавной заливки до конца."""
    for _ in range(100):
        if button.progress() == button.targetProgress():
            return
        QTest.qWait(20)


def type_text(window: TTSApp, content: str) -> None:
    """Имитирует ввод: сигнал textChanged должен сработать по-настоящему."""
    window.text_area.insertPlainText(content)
    QApplication.processEvents()


def find_buttons(window: TTSApp) -> list[str]:
    return [button.text() for button in window.findChildren(QPushButton)]


def patch_about_dialog(
    monkeypatch: pytest.MonkeyPatch, seen: list[QDialog]
) -> None:
    """Подменяет модальный показ, но проверяет работу кнопки OK."""

    def fake_exec(dialog: QDialog) -> int:
        seen.append(dialog)
        assert dialog.windowTitle() == "О программе"
        ok_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "OK"
        ]
        assert len(ok_buttons) == 1
        ok_buttons[0].click()
        return int(dialog.result())

    monkeypatch.setattr(QDialog, "exec", fake_exec)


# --- Окно ---

def test_window_creates(window: TTSApp) -> None:
    assert window.windowTitle().startswith("TextToSpeech")


def test_window_geometry(window: TTSApp) -> None:
    assert window.width() >= 640, f"окно слишком узкое: {window.width()}"
    assert window.height() >= 520, f"окно слишком низкое: {window.height()}"


def test_system_title_bar_disabled(window: TTSApp) -> None:
    assert isinstance(window.menuBar(), QMenuBar)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint


def test_window_corners_are_rounded(window: TTSApp) -> None:
    """Прозрачный фон и радиус в стилях дают скруглённые углы."""
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert f"border-top-left-radius: {WINDOW_RADIUS}px" in STYLE_SHEET
    assert f"border-top-right-radius: {WINDOW_RADIUS}px" in STYLE_SHEET
    assert f"border-bottom-right-radius: {WINDOW_RADIUS}px" in STYLE_SHEET
    assert "QWidget#titleCorner { background: transparent;" in STYLE_SHEET

    mask = window.mask()
    assert not mask.isEmpty()
    assert not mask.contains(QPoint(0, 0))
    assert not mask.contains(QPoint(window.width() - 1, 0))
    assert mask.contains(QPoint(window.width() // 2, 5))

    corner = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    assert corner is not None
    assert corner.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_content_has_inset_from_window_edges(window: TTSApp) -> None:
    margins = window.centralWidget().layout().contentsMargins()
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == (WINDOW_INSET, WINDOW_INSET, WINDOW_INSET, WINDOW_INSET)

    corner = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    assert corner is not None
    title_margins = corner.layout().contentsMargins()
    assert min(
        title_margins.left(),
        title_margins.top(),
        title_margins.right(),
        title_margins.bottom(),
    ) >= 4


def test_title_buttons_in_menu_bar(window: TTSApp) -> None:
    """Кнопки окна находятся в правой части строки меню."""
    corner = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    assert corner is not None
    labels = [button.text() for button in corner.findChildren(QPushButton)]
    assert labels == [TITLE_MINIMIZE, TITLE_MAXIMIZE, TITLE_CLOSE]


def test_title_buttons_have_handlers(window: TTSApp) -> None:
    assert window.min_button.toolTip() == "Свернуть"
    assert window.max_button.toolTip() == "Развернуть"
    assert window.close_button.toolTip() == "Закрыть"


def test_title_buttons_are_frameless(window: TTSApp) -> None:
    """Все три кнопки используют один стиль без системной рамки."""
    assert window.close_button.objectName() == "CloseButton"
    assert "QPushButton#TitleButton, QPushButton#CloseButton" in STYLE_SHEET


def test_build_window_shows_it(qapp: QApplication) -> None:
    window = build_window()
    assert window.isVisible()
    window.close()
    qapp.processEvents()


def test_build_window_centers_on_screen(qapp: QApplication) -> None:
    screen = qapp.primaryScreen()
    if screen is None:
        pytest.skip("нет доступного экрана")

    window = build_window()
    qapp.processEvents()

    center = screen.availableGeometry().center()
    frame = window.frameGeometry().center()
    # Оффскрин-платформа может сдвинуть рамку на пару пикселей.
    assert abs(frame.x() - center.x()) <= 5
    assert abs(frame.y() - center.y()) <= 5
    window.close()


# --- Виджеты ---

def test_text_area_exists(window: TTSApp) -> None:
    assert window.text_area is not None


def test_app_icon_file_exists() -> None:
    assert APP_ICON_PATH.is_file(), f"нет иконки: {APP_ICON_PATH}"


def test_app_icon_shown_before_title(window: TTSApp) -> None:
    """Иконка окна и маленькая иконка перед названием."""
    assert not window.windowIcon().isNull()

    labels = {
        label.objectName(): label
        for label in window.findChildren(QLabel)
        if label.objectName() in {"AppIcon", "Title"}
    }
    icon = labels["AppIcon"]
    title = labels["Title"]
    assert not icon.pixmap().isNull()
    assert icon.pixmap().width() <= APP_ICON_SIZE
    assert icon.geometry().left() < title.geometry().left()


def test_wave_is_in_header_after_title(window: TTSApp, qapp: QApplication) -> None:
    """Волна видна всегда и стоит в шапке сразу после названия."""
    assert isinstance(window.progress, SoundWaveProgress)
    assert window.progress.isVisible()

    title = next(
        label
        for label in window.findChildren(QLabel)
        if label.objectName() == "Title"
    )
    assert title.parent() is window.progress.parent()
    assert window.progress.geometry().left() >= title.geometry().right()
    assert window.progress.width() >= window.centralWidget().width() // 3
    assert window.progress.parent() is not window.stop_button.parent()
    assert not window.progress.isTextVisible()

    window.progress.setValue(60)
    assert window.progress.value() == 60


def test_wave_has_purple_layer_filled_with_progress(
    window: TTSApp, qapp: QApplication
) -> None:
    """Вторая волна фиолетовая и растёт слева направо вместе с синей."""
    window.progress.setValue(50)
    qapp.processEvents()

    image = window.progress.grab().toImage()
    def positions_of(color: QColor, tolerance: int) -> list[int]:
        found = []
        for x in range(image.width()):
            for y in range(image.height()):
                actual = QColor(image.pixel(x, y))
                if (
                    abs(actual.red() - color.red()) < tolerance
                    and abs(actual.green() - color.green()) < tolerance
                    and abs(actual.blue() - color.blue()) < tolerance
                ):
                    found.append(x)
                    break
        return found

    xs = positions_of(QColor(WAVE_PURPLE), 50)
    assert xs
    assert max(xs) <= image.width() * 50 // 100 + 2

    green_xs = positions_of(QColor(WAVE_GREEN), 40)
    assert green_xs
    assert max(green_xs) <= image.width() * 50 // 100 + 2

    # Незаполненная часть дорожки светло-бирюзовая, а не серая.
    track = QColor(image.pixel(image.width() * 3 // 4, image.height() // 2))
    expected = QColor(WAVE_TRACK)
    assert (
        abs(track.red() - expected.red()) < 12
        and abs(track.green() - expected.green()) < 12
        and abs(track.blue() - expected.blue()) < 12
    )


def test_control_buttons_stay_right_aligned(
    window: TTSApp, qapp: QApplication
) -> None:
    """«Стоп» и «Озвучить» не растягиваются и прижаты к правому краю."""
    panel = window.speak_button.parent()
    assert panel is window.stop_button.parent()
    assert panel is not window.progress.parent()
    qapp.processEvents()

    right_margin = panel.layout().contentsMargins().right()
    assert panel.rect().right() - window.speak_button.geometry().right() <= (
        right_margin + 2
    )
    for button in (window.stop_button, window.speak_button):
        assert button.width() <= button.sizeHint().width() + 2
    assert window.stop_button.geometry().right() < window.speak_button.geometry().left()


def test_wave_tracks_playback_position(window: TTSApp) -> None:
    """Волна показывает позицию воспроизведения, а не ход синтеза."""
    window.progress.setValue(0)
    window._on_playback_duration(1000)

    window._on_playback_position(250)
    assert window.progress.value() == 25

    window._on_playback_position(1000)
    assert window.progress.value() == 100


def test_wave_animates_only_during_playback(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Анимация выключается при остановке, волна доходит до конца файла."""
    window.progress.setPlaying(True)
    assert window.progress.isPlaying()

    monkeypatch.setattr(
        QMediaPlayer,
        "mediaStatus",
        lambda _self: QMediaPlayer.MediaStatus.EndOfMedia,
    )
    window._on_playback_state(QMediaPlayer.PlaybackState.StoppedState)

    assert not window.progress.isPlaying()
    assert window.progress.value() == 100
    assert "Воспроизведение завершено" in window.status_label.text()


def test_wave_stays_full_when_stop_arrives_before_end_of_media(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qt присылает StoppedState с BufferedMedia — это тоже конец файла."""
    window.progress.setPlaying(True)
    window.progress.setValue(96)
    window._playback_duration_ms = 1000
    window.stop_button.setEnabled(True)

    monkeypatch.setattr(
        QMediaPlayer,
        "mediaStatus",
        lambda _self: QMediaPlayer.MediaStatus.BufferedMedia,
    )
    monkeypatch.setattr(QMediaPlayer, "position", lambda _self: 1000)
    window._on_playback_state(QMediaPlayer.PlaybackState.StoppedState)

    assert not window.progress.isPlaying()
    assert window.progress.value() == 100
    assert not window.stop_button.isEnabled()
    assert "Воспроизведение завершено" in window.status_label.text()


def test_media_status_end_of_media_finishes_playback(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Поздний EndOfMedia тоже оставляет волну заполненной."""
    window.progress.setPlaying(True)
    window.progress.setValue(88)
    monkeypatch.setattr(
        QMediaPlayer,
        "mediaStatus",
        lambda _self: QMediaPlayer.MediaStatus.EndOfMedia,
    )

    window._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)

    assert window.progress.value() == 100
    assert not window.progress.isPlaying()
    assert "Воспроизведение завершено" in window.status_label.text()


def test_playback_error_shows_russian_status(window: TTSApp) -> None:
    """Ошибка плеера обнуляет волну и пишет понятный статус."""
    window.progress.setPlaying(True)
    window.progress.setValue(50)
    window.stop_button.setEnabled(True)

    window._on_playback_error(QMediaPlayer.Error.FormatError, "codec missing")

    assert window.progress.value() == 0
    assert not window.progress.isPlaying()
    assert not window.stop_button.isEnabled()
    assert "Неподдерживаемый формат аудио" in window.status_label.text()


def test_saved_output_dir_is_read_from_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Сохранённая папка используется при следующем запуске."""
    monkeypatch.setattr(
        "texttospeech.app.QSettings",
        lambda *_args: SimpleNamespace(value=lambda *_a, **_k: str(tmp_path)),
    )
    assert saved_output_dir() == tmp_path

    monkeypatch.setattr(
        "texttospeech.app.QSettings",
        lambda *_args: SimpleNamespace(value=lambda *_a, **_k: ""),
    )
    assert saved_output_dir() == OUTPUT_DIR


def test_output_dir_can_be_changed_in_settings(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Кнопка в «Настройках» меняет папку и запоминает выбор."""
    values: dict[str, str] = {}

    class FakeSettings:
        def value(self, key: str, default: str = "", type=None) -> str:
            return values.get(key, default)

        def setValue(self, key: str, value: str) -> None:
            values[key] = value

        def sync(self) -> None:
            pass

    window._qsettings = FakeSettings()  # type: ignore[assignment]
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr("texttospeech.app.configure_logging", lambda path: path)

    window._choose_output_dir()

    assert window.output_dir == tmp_path
    assert window.output_button.text() == str(tmp_path)
    assert values["outputDir"] == str(tmp_path)
    assert "Папка для файлов" in window.status_label.text()


def test_synthesis_progress_fills_button_not_wave(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ход синтеза идёт в заливку кнопки, волна не трогается."""
    assert isinstance(window.speak_button, ProgressButton)

    window.output_dir = tmp_path
    monkeypatch.setattr(Voice, "is_downloaded", property(lambda self: True))
    monkeypatch.setattr("texttospeech.app.split_text", lambda text: ["а", "б"])
    def fake_concat(paths, dest):
        dest.write_text("wav", encoding="utf-8")
        return 1.0

    monkeypatch.setattr("texttospeech.app.concat_wavs", fake_concat)

    events: list[tuple[str, object]] = []

    class RecordingQueue(queue.Queue):
        def put(self, item, *args: object, **kwargs: object) -> None:
            events.append(item)
            super().put(item, *args, **kwargs)  # type: ignore[arg-type]

    window.events = RecordingQueue()  # type: ignore[assignment]
    window.progress.setValue(37)

    class FakeEngine:
        name = "fake"

        def prepare(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("модель уже загружена")

        def synthesize(self, chunk, voice, dest, speed=1.0):
            dest.write_text("wav", encoding="utf-8")
            return SimpleNamespace(path=dest)

    voice = Voice(key="fake", title="Test", gender="female")
    window._synthesize_worker("текст", voice, 1.0, FakeEngine())

    synthesis = [value for kind, value in events if kind == "synthesis_progress"]
    assert synthesis == [47, 95, 100]
    assert any(kind == "done" for kind, _ in events)
    assert not any(kind in {"download", "progress"} for kind, _ in events)
    assert window.progress.value() == 37
    # После успешной склейки фрагменты и их пустая папка удалены.
    assert not (tmp_path / "parts").exists()
    assert (tmp_path / "fake_1x.wav").exists()


def test_button_fill_grows_left_to_right(window: TTSApp) -> None:
    """Граница заливки кнопки сдвигается вправо по мере синтеза."""
    button = window.speak_button
    button.setProgress(0)
    assert button.progress() == 0
    assert button.styleSheet() == ""

    button.setProgress(25)
    settle_progress(button)
    quarter = button.styleSheet()
    assert button.progress() == 25
    assert "x1:0, y1:0, x2:1, y2:0" in quarter
    assert "stop:0.2500" in quarter

    button.setProgress(75)
    settle_progress(button)
    three_quarters = button.styleSheet()
    assert "stop:0.7500" in three_quarters
    assert three_quarters != quarter

    window._handle_event("synthesis_progress", 100)
    settle_progress(button)
    assert button.progress() == 100
    assert "stop:1.0000" in button.styleSheet()


def test_button_fill_does_not_jump_instantly(window: TTSApp) -> None:
    """Даже пачка событий 0 → 100 отрисовывается постепенно."""
    button = window.speak_button
    button.setProgress(0)
    button.setProgress(100)

    assert button.targetProgress() == 100
    assert button.progress() < 100

    settle_progress(button)
    assert button.progress() == 100


def test_buttons_present(window: TTSApp) -> None:
    labels = find_buttons(window)
    assert "Открыть файл" in labels, f"нет кнопки открытия: {labels}"
    assert "Вставить текст из буфера" in labels, f"нет кнопки вставки: {labels}"
    assert "Озвучить" in labels, f"нет кнопки озвучивания: {labels}"


def test_no_engine_info_on_main_page(window: TTSApp) -> None:
    """Сведения о движке перенесены в «О программе»."""
    labels = window.centralWidget().findChildren(QLabel)
    texts = [label.text() for label in labels]
    assert not any("Piper" in text or "движк" in text.lower() for text in texts), (
        f"на главной странице осталась информация о движке: {texts}"
    )


def test_empty_state(window: TTSApp) -> None:
    """До открытия файла текст пуст и путь не выбран."""
    assert window.current_path is None
    assert window.text_area.toPlainText().strip() == ""


# --- Меню ---

def test_main_menus_present(window: TTSApp) -> None:
    titles = [action.text() for action in window.menuBar().actions()]
    assert "Настройки" in titles
    assert "О программе" in titles


def test_settings_menu_holds_all_controls(window: TTSApp) -> None:
    """Все настройки живут в отдельном меню, а не на главной странице."""
    actions = window.settings_menu.actions()
    assert len(actions) == 1
    assert isinstance(actions[0], QWidgetAction)
    panel = actions[0].defaultWidget()
    assert panel is not None

    for selector in (
        window.engine_box,
        window.voice_box,
        window.speed_box,
    ):
        assert selector.parent() is panel
        assert isinstance(selector, DropdownButton)


def test_about_is_top_level_action(window: TTSApp) -> None:
    """«О программе» не имеет вложенного меню."""
    titles = [action.text() for action in window.menuBar().actions()]
    assert titles.count("О программе") == 1
    assert window.about_action.text() == "О программе"
    assert window.about_action.menu() is None


def test_about_describes_engine_and_usage(window: TTSApp) -> None:
    text = window.about_text()
    assert "Piper" in text
    assert "Silero" in text
    assert "Настройки" in text
    assert "буфера" in text
    assert "Озвучить" in text


def test_show_about_has_working_ok_button(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кнопка OK закрывает диалог, а не остаётся декорацией."""
    seen: list[QDialog] = []
    patch_about_dialog(monkeypatch, seen)
    window.show_about()

    assert len(seen) == 1
    assert seen[0].result() == QDialog.DialogCode.Accepted


def test_clicking_about_action_opens_dialog(
    window: TTSApp, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Клик по пункту меню реально открывает справку."""
    seen: list[QDialog] = []
    patch_about_dialog(monkeypatch, seen)

    menu_bar = window.menuBar()
    action_rect = menu_bar.actionGeometry(window.about_action)
    QTest.mouseClick(menu_bar, Qt.MouseButton.LeftButton, pos=action_rect.center())
    qapp.processEvents()

    assert len(seen) == 1


# --- Выпадающие списки ---

def test_voice_and_speed_are_menu_buttons(window: TTSApp) -> None:
    """Вместо системных QComboBox — кнопки с меню и шевроном."""
    assert not hasattr(window, "quality_box")
    assert isinstance(window.voice_box, DropdownButton)
    assert isinstance(window.speed_box, DropdownButton)
    assert not window.voice_box.icon().isNull()


def test_voice_selection_changes_voice(window: TTSApp) -> None:
    voices = voices_for_quality(window.selected_quality, window.selected_engine_key)
    other = next(v for v in voices if v.key != window.selected_voice.key)

    window.voice_box.setCurrentText(other.label)

    assert window.selected_voice == other
    assert window.voice_box.text() == other.label


def test_speed_selection_changes_speed(window: TTSApp) -> None:
    window.speed_box.setCurrentText("2.0x")

    assert window.selected_speed == 2.0
    assert window.speed_box.text() == "2.0x"


def test_default_engine_is_silero_with_xenia(window: TTSApp) -> None:
    """При запуске сразу выбран Silero и голос Ксения (xenia)."""
    assert DEFAULT_ENGINE == "silero"
    assert window.selected_engine_key == "silero"
    assert window.selected_voice.key == DEFAULT_SILERO_VOICE_KEY
    assert window.selected_voice.name == "xenia"
    assert window.selected_voice.sample_rate == 48000


def test_quality_is_fixed_without_ui(window: TTSApp) -> None:
    """В настройках нет качества: Silero 48 кГц, Piper medium."""
    assert not hasattr(window, "quality_box")
    assert window.selected_quality == "48000"
    assert window.selected_voice.sample_rate == 48000

    window.engine_box.setCurrentText("Piper")
    assert window.selected_quality == "medium"
    assert window.selected_voice.engine == "piper"


def test_engine_selection_switches_to_piper(window: TTSApp) -> None:
    """Выбор Piper меняет голос, качество остаётся фиксированным."""
    window.engine_box.setCurrentText("Piper")

    assert window.selected_engine_key == "piper"
    assert window.selected_voice.engine == "piper"
    assert [action.text() for action in window.voice_box._menu.actions()] == [
        voice.label for voice in CATALOG
    ]


def test_silero_quality_stays_at_48k(window: TTSApp) -> None:
    """При возврате к Silero качество по-прежнему 48 кГц."""
    window.engine_box.setCurrentText("Piper")
    window.engine_box.setCurrentText("Silero")

    assert window.selected_quality == "48000"
    assert window.selected_voice.sample_rate == 48000
    assert [action.text() for action in window.voice_box._menu.actions()] == [
        voice.label for voice in voices_for_quality("48000", "silero")
    ]


def test_engine_switch_remembers_voice_settings(window: TTSApp) -> None:
    """Голос и скорость не сбрасываются при смене движка."""
    window.engine_box.setCurrentText("Piper")
    window.voice_box.setCurrentText("Денис")
    window.speed_box.setCurrentText("2.0x")

    window.engine_box.setCurrentText("Silero")
    window.voice_box.setCurrentText("Евгений")
    window.speed_box.setCurrentText("1.5x")

    window.engine_box.setCurrentText("Piper")
    assert window.selected_voice.name == "denis"
    assert window.selected_speed == 2.0

    window.engine_box.setCurrentText("Silero")
    assert window.selected_voice.name == "eugene"
    assert window.selected_voice.sample_rate == 48000
    assert window.speed_box.currentText() == "1.5x"


# --- Редактирование ---

def test_text_area_is_editable(window: TTSApp) -> None:
    assert not window.text_area.isReadOnly()


def test_typing_marks_dirty(window: TTSApp) -> None:
    assert window.dirty is False

    type_text(window, "Привет")

    assert window.dirty is True


def test_save_button_enabled_only_when_dirty(window: TTSApp) -> None:
    assert window.save_button.isEnabled() is False

    type_text(window, "изменение")
    assert window.save_button.isEnabled() is True

    window._set_dirty(False)
    assert window.save_button.isEnabled() is False


def test_current_text_reflects_edits(window: TTSApp) -> None:
    type_text(window, "Новый текст")
    assert window.current_text == "Новый текст"


# --- Буфер обмена ---

def test_paste_inserts_at_cursor(window: TTSApp, qapp: QApplication) -> None:
    qapp.clipboard().setText("из буфера")
    # insertPlainText оставляет курсор в конце введённого текста.
    type_text(window, "Начало ")

    window.paste_from_clipboard()

    assert window.current_text == "Начало из буфера"
    assert window.dirty is True
    assert "Вставлено из буфера" in window.status_label.text()


def test_paste_empty_clipboard_reports_error(window: TTSApp, qapp: QApplication) -> None:
    qapp.clipboard().clear()

    window.paste_from_clipboard()

    assert window.current_text == ""
    assert "Буфер обмена пуст" in window.status_label.text()


def test_title_marks_unsaved(window: TTSApp, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("исходный", encoding="utf-8")
    window._load_path(source)

    assert "*" not in window.windowTitle()

    type_text(window, "!")
    assert "*" in window.windowTitle(), "звездочка в заголовке не появилась"

    window.save_file()
    assert "*" not in window.windowTitle()


def test_path_label_marks_unsaved(window: TTSApp, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("исходный", encoding="utf-8")
    window._load_path(source)

    assert "изменён" not in window.path_label.text()

    type_text(window, "!")
    assert "изменён" in window.path_label.text()


def test_loading_file_does_not_mark_dirty(window: TTSApp, tmp_path: Path) -> None:
    """Загрузка файла — не пользовательская правка."""
    source = tmp_path / "t.txt"
    source.write_text("содержимое файла", encoding="utf-8")

    window._load_path(source)

    assert window.dirty is False
    assert window.current_text == "содержимое файла"


# --- Сохранение ---

def test_save_writes_to_same_file(window: TTSApp, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("было", encoding="utf-8")
    window._load_path(source)

    type_text(window, " стало")
    window.save_file()

    assert source.read_text(encoding="utf-8") == "было стало"
    assert window.dirty is False


def test_save_keeps_original_encoding(window: TTSApp, tmp_path: Path) -> None:
    """Файл в windows-1251 должен остаться в windows-1251."""
    source = tmp_path / "t.txt"
    source.write_bytes("было".encode("cp1251"))
    window._load_path(source)

    type_text(window, " стало")
    window.save_file()

    assert source.read_bytes() == "было стало".encode("cp1251")


def test_save_without_file_asks_path(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_path(*_args, **_kwargs):
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", no_path)

    type_text(window, "текст без файла")
    window.save_file()

    assert window.current_path is None, "без выбранного пути файл не должен появиться"


def test_save_reports_error(window: TTSApp, tmp_path: Path) -> None:
    source = tmp_path / "sub" / "t.txt"  # папки нет — запись провалится
    window.current_path = source
    type_text(window, "данные")

    window.save_file()

    assert "Не удалось сохранить" in window.status_label.text()


# --- Несохранённые изменения ---

def test_cancel_keeps_everything(window: TTSApp, tmp_path: Path) -> None:
    """Отмена в диалоге не должна ничего терять."""
    source = tmp_path / "t.txt"
    source.write_text("первый", encoding="utf-8")
    window._load_path(source)
    type_text(window, " правка")

    def cancel(_action: str) -> bool:
        return False

    window._confirm_discard = cancel  # type: ignore[method-assign]
    window.clear_file()

    assert window.current_path == source
    assert window.current_text == "первый правка"
    assert window.dirty is True


def test_discard_drops_changes(window: TTSApp, tmp_path: Path) -> None:
    """Ответ «Не сохранять» отбрасывает правки."""
    source = tmp_path / "t.txt"
    source.write_text("первый", encoding="utf-8")
    window._load_path(source)
    type_text(window, " правка")

    def discard(_action: str) -> bool:
        return True

    window._confirm_discard = discard  # type: ignore[method-assign]
    window.clear_file()

    assert window.current_path is None
    assert window.current_text == ""


def test_discard_prompt_not_shown_when_clean(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class FakeMessageBox:
        def __init__(self, *_args, **_kwargs):
            calls.append("prompt")

        @staticmethod
        def exec() -> int:
            return int(QMessageBox.StandardButton.Discard)

    monkeypatch.setattr("texttospeech.app.QMessageBox", FakeMessageBox)
    window.clear_file()

    assert not calls, "чистый файл не должен спрашивать"


def test_discard_prompt_buttons_are_russian(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Предупреждение при выходе не содержит английских подписей."""
    window.dirty = True
    labels: list[str] = []

    def fake_exec(box: QMessageBox) -> int:
        buttons = box.buttons()
        labels.extend(button.text() for button in buttons)
        discard = next(
            button
            for button in buttons
            if button.objectName() == "DiscardButton"
        )
        discard.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    assert window._confirm_discard("Закрыть программу?")
    assert set(labels) == {"Сохранить", "Не сохранять", "Отмена"}


# --- Загрузка файла ---

def test_open_file_loads_text(
    window: TTSApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample = tmp_path / "speech.txt"
    sample.write_text("Привет! Это тестовый текст.", encoding="utf-8")

    def chosen(*_args, **_kwargs):
        return str(sample), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", chosen)
    window.open_file()

    assert window.current_path == sample
    assert "тестовый текст" in window.text_area.toPlainText()


def test_open_file_updates_status(window: TTSApp, tmp_path: Path) -> None:
    sample = tmp_path / "a.txt"
    sample.write_text("одно два три", encoding="utf-8")
    window._load_path(sample)
    status = window.status_label.text()

    assert "3" in status, f"в статусе нет числа слов: {status}"


def test_clear_file_resets(window: TTSApp) -> None:
    sample = Path("dummy.txt")
    window._load_path(sample)

    def discard(_action: str) -> bool:
        return True

    window._confirm_discard = discard  # type: ignore[method-assign]
    window.clear_file()

    assert window.current_path is None
    assert window.text_area.toPlainText().strip() == ""


def test_missing_file_reports_error(window: TTSApp, tmp_path: Path) -> None:
    window._load_path(tmp_path / "нет-такого.txt")

    assert window.current_path is None
    assert "Не удалось прочитать файл" in window.status_label.text()


# --- Чтение кодировок ---

def test_read_utf8(tmp_path: Path) -> None:
    f = tmp_path / "u.txt"
    f.write_text("Привет", encoding="utf-8")

    content, encoding = read_text_file(f)
    assert content == "Привет"
    assert "utf-8" in encoding


def test_read_cp1251(tmp_path: Path) -> None:
    f = tmp_path / "w.txt"
    f.write_bytes("Привет".encode("cp1251"))

    content, _ = read_text_file(f)
    assert content == "Привет", "русский текст в windows-1251 прочитан неверно"


def test_read_utf8_bom(tmp_path: Path) -> None:
    f = tmp_path / "bom.txt"
    f.write_bytes("Привет".encode("utf-8-sig"))

    content, encoding = read_text_file(f)
    assert content == "Привет"
    assert encoding == "utf-8-sig"


def test_plain_utf8_not_treated_as_bom(tmp_path: Path) -> None:
    """Обычный utf-8 не должен помечаться как utf-8-sig."""
    f = tmp_path / "plain.txt"
    f.write_text("Привет", encoding="utf-8")

    _, encoding = read_text_file(f)
    assert encoding == "utf-8"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1251"])
def test_roundtrip_keeps_bytes(tmp_path: Path, encoding: str) -> None:
    """Открыть и сохранить без правок — байт в байт."""
    f = tmp_path / f"f_{encoding}.txt"
    original = "Привет мир"
    f.write_bytes(original.encode(encoding))

    content, detected = read_text_file(f)
    f.write_bytes(content.encode(detected))

    assert f.read_bytes() == original.encode(encoding), (
        f"кодировка {encoding} изменилась при перезаписи"
    )


# --- Склонение слов ---

@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "символ"), (2, "символа"), (5, "символов"),
        (11, "символов"), (12, "символов"), (14, "символов"),
        (21, "символ"), (22, "символа"), (25, "символов"),
        (0, "символов"), (100, "символов"), (101, "символ"),
    ],
)
def test_plural_ru(number: int, expected: str) -> None:
    assert plural_ru(number, "символ", "символа", "символов") == expected
