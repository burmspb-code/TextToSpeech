"""Smoke-тесты интерфейса."""
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter", reason="Tkinter недоступен на этой платформе")

from texttospeech.app import (  # noqa: E402
    TTSApp,
    build_window,
    plural_ru,
    read_text_file,
)


@pytest.fixture(scope="session")
def root():
    """Одно окно на всю сессию.

    Tkinter не любит, когда корневых окон несколько: после destroy()
    первого корня следующий Tk() падает с TclError.
    """
    window = build_window()
    yield window
    window.destroy()


@pytest.fixture
def app(root) -> TTSApp:
    # Сбрасываем состояние напрямую: dirty=False делает подтверждение
    # при очистке ненужным, иначе тест завис бы на модальном окне.
    root.tts_app._set_text("")
    root.tts_app.current_path = None
    root.tts_app.current_encoding = None
    root.tts_app._set_dirty(False)
    return root.tts_app


@pytest.fixture
def quiet_dialogs(monkeypatch):
    """Подменяет модальные диалоги, чтобы тесты не висели."""
    calls: list[str] = []

    def askyesnocancel(*args, **kwargs):
        calls.append("askyesnocancel")
        return None

    def asksaveasfilename(*args, **kwargs):
        calls.append("asksaveasfilename")
        return ""

    def askopenfilename(*args, **kwargs):
        calls.append("askopenfilename")
        return ""

    monkeypatch.setattr("texttospeech.app.messagebox.askyesnocancel", askyesnocancel)
    monkeypatch.setattr("texttospeech.app.filedialog.asksaveasfilename", asksaveasfilename)
    monkeypatch.setattr("texttospeech.app.filedialog.askopenfilename", askopenfilename)
    return calls


def type_text(app: TTSApp, content: str) -> None:
    """Имитирует ввод с клавиатуры: событие <<Modified>> нужно настоящее."""
    app.text_area.insert("end", content)
    app.text_area.edit_modified(True)
    app._on_text_modified()


def find_widgets(root, widget_type):
    """Ищет виджеты по всему дереву, а не только среди прямых потомков."""
    found = []
    for child in root.winfo_children():
        if isinstance(child, widget_type):
            found.append(child)
        found.extend(find_widgets(child, widget_type))
    return found


# --- Окно ---

def test_window_creates(root) -> None:
    assert root.winfo_exists() == 1
    assert root.title().startswith("TextToSpeech")


def test_window_geometry(root) -> None:
    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()

    assert width >= 640, f"окно слишком узкое: {width}"
    assert height >= 480, f"окно слишком низкое: {height}"


# --- Виджеты ---

def test_text_area_exists(root) -> None:
    assert find_widgets(root, tk.Text), "в окне нет поля для текста"


def test_buttons_present(root) -> None:
    """Должны быть кнопки открытия и озвучивания."""
    from tkinter import ttk

    labels = []
    for button in find_widgets(root, ttk.Button):
        try:
            labels.append(button.cget("text"))
        except tk.TclError:
            pass

    assert "Открыть файл" in labels, f"нет кнопки открытия: {labels}"
    assert "Озвучить" in labels, f"нет кнопки озвучивания: {labels}"


def test_empty_state(app) -> None:
    """До открытия файла текст пуст и путь не выбран."""
    assert app.current_path is None
    assert app.text_area.get("1.0", "end").strip() == ""


# --- Редактирование ---

def test_text_area_is_editable(app) -> None:
    """Поле должно быть доступно для ввода, а не только для чтения."""
    assert str(app.text_area.cget("state")) == "normal"


def test_typing_marks_dirty(app) -> None:
    assert app.dirty is False

    type_text(app, "Привет")

    assert app.dirty is True


def test_save_button_enabled_only_when_dirty(app) -> None:
    assert str(app.save_button.cget("state")) == "disabled"

    type_text(app, "изменение")
    assert str(app.save_button.cget("state")) == "normal"

    app._set_dirty(False)
    assert str(app.save_button.cget("state")) == "disabled"


def test_current_text_reflects_edits(app) -> None:
    type_text(app, "Новый текст")
    assert app.current_text == "Новый текст"


def test_title_marks_unsaved(app, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("исходный", encoding="utf-8")
    app._load_path(source)

    assert "*" not in app.root.title()

    type_text(app, "!")
    assert "*" in app.root.title(), "звездочка в заголовке не появилась"

    app.save_file()
    assert "*" not in app.root.title()


def test_path_label_marks_unsaved(app, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("исходный", encoding="utf-8")
    app._load_path(source)

    assert "изменён" not in app.path_label.cget("text")

    type_text(app, "!")
    assert "изменён" in app.path_label.cget("text")


def test_loading_file_does_not_mark_dirty(app, tmp_path: Path) -> None:
    """Загрузка файла — не пользовательская правка."""
    source = tmp_path / "t.txt"
    source.write_text("содержимое файла", encoding="utf-8")

    app._load_path(source)

    assert app.dirty is False
    assert app.current_text == "содержимое файла"


# --- Сохранение ---

def test_save_writes_to_same_file(app, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("было", encoding="utf-8")
    app._load_path(source)

    type_text(app, " стало")
    app.save_file()

    assert source.read_text(encoding="utf-8") == "было стало"
    assert app.dirty is False


def test_save_keeps_original_encoding(app, tmp_path: Path) -> None:
    """Файл в windows-1251 должен остаться в windows-1251."""
    source = tmp_path / "t.txt"
    source.write_bytes("было".encode("cp1251"))
    app._load_path(source)

    type_text(app, " стало")
    app.save_file()

    assert source.read_bytes() == "было стало".encode("cp1251")


def test_save_without_file_asks_path(app, quiet_dialogs, tmp_path: Path) -> None:
    type_text(app, "текст без файла")
    app.save_file()

    assert "asksaveasfilename" in quiet_dialogs
    assert app.current_path is None, "без выбранного пути файл не должен появиться"


def test_save_reports_error(app, tmp_path: Path) -> None:
    source = tmp_path / "sub" / "t.txt"  # папки нет — запись провалится
    app.current_path = source
    type_text(app, "данные")

    app.save_file()

    assert "Не удалось сохранить" in app.status_label.cget("text")
    assert str(app.status_label.cget("foreground")) == "#CF222E"


# --- Несохранённые изменения ---

def test_cancel_keeps_everything(app, quiet_dialogs, tmp_path: Path) -> None:
    """Отмена в диалоге не должна ничего терять."""
    source = tmp_path / "t.txt"
    source.write_text("первый", encoding="utf-8")
    app._load_path(source)
    type_text(app, " правка")

    app.clear_file()  # диалог вернёт None (отмена)

    assert app.current_path == source
    assert app.current_text == "первый правка"
    assert app.dirty is True


def test_discard_drops_changes(app, quiet_dialogs, monkeypatch, tmp_path: Path) -> None:
    """Ответ «Нет» отбрасывает правки."""
    monkeypatch.setattr("texttospeech.app.messagebox.askyesnocancel", lambda *a, **k: False)

    source = tmp_path / "t.txt"
    source.write_text("первый", encoding="utf-8")
    app._load_path(source)
    type_text(app, " правка")

    app.clear_file()

    assert app.current_path is None
    assert app.current_text == ""


def test_discard_prompt_not_shown_when_clean(app, quiet_dialogs, tmp_path: Path) -> None:
    source = tmp_path / "t.txt"
    source.write_text("первый", encoding="utf-8")
    app._load_path(source)

    app.clear_file()

    assert "askyesnocancel" not in quiet_dialogs, "чистый файл не должен спрашивать"


# --- Загрузка файла ---

def test_open_file_loads_text(app, root, tmp_path: Path) -> None:
    sample = tmp_path / "speech.txt"
    sample.write_text("Привет! Это тестовый текст.", encoding="utf-8")

    app._load_path(sample)
    root.update_idletasks()

    assert app.current_path == sample
    assert "тестовый текст" in app.text_area.get("1.0", "end")


def test_open_file_updates_status(app, root, tmp_path: Path) -> None:
    sample = tmp_path / "a.txt"
    sample.write_text("одно два три", encoding="utf-8")

    app._load_path(sample)
    status = app.status_label.cget("text")

    assert "3" in status, f"в статусе нет числа слов: {status}"


def test_clear_file_resets(app) -> None:
    sample = Path("dummy.txt")
    app._load_path(sample)
    app.clear_file()

    assert app.current_path is None
    assert app.text_area.get("1.0", "end").strip() == ""


def test_missing_file_reports_error(app, tmp_path: Path) -> None:
    app._load_path(tmp_path / "нет-такого.txt")

    assert app.current_path is None
    assert str(app.status_label.cget("foreground")) == "#CF222E"


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
    assert content == "Привет", "BOM не удалён"
    assert encoding == "utf-8-sig"


def test_plain_utf8_not_treated_as_bom(tmp_path: Path) -> None:
    """Обычный utf-8 не должен помечаться как utf-8-sig.

    Иначе при сохранении в файл попал бы лишний BOM. Это регрессия,
    найденная тестом на круговую запись.
    """
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