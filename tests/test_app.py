"""Smoke-тесты интерфейса на PyQt6."""
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from texttospeech.app import TTSApp, build_window, plural_ru, read_text_file


def type_text(window: TTSApp, content: str) -> None:
    """Имитирует ввод: сигнал textChanged должен сработать по-настоящему."""
    window.text_area.insertPlainText(content)
    QApplication.processEvents()


def find_buttons(window: TTSApp) -> list[str]:
    return [button.text() for button in window.findChildren(QPushButton)]


# --- Окно ---

def test_window_creates(window: TTSApp) -> None:
    assert window.windowTitle().startswith("TextToSpeech")


def test_window_geometry(window: TTSApp) -> None:
    assert window.width() >= 640, f"окно слишком узкое: {window.width()}"
    assert window.height() >= 520, f"окно слишком низкое: {window.height()}"


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


def test_buttons_present(window: TTSApp) -> None:
    labels = find_buttons(window)
    assert "Открыть файл" in labels, f"нет кнопки открытия: {labels}"
    assert "Озвучить" in labels, f"нет кнопки озвучивания: {labels}"


def test_empty_state(window: TTSApp) -> None:
    """До открытия файла текст пуст и путь не выбран."""
    assert window.current_path is None
    assert window.text_area.toPlainText().strip() == ""


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
