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
    root.tts_app.clear_file()
    return root.tts_app


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

    content, _ = read_text_file(f)
    assert content == "Привет", "BOM не удалён"


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