"""Smoke-тест интерфейса: окно должно создаваться без ошибок."""
import pytest

tk = pytest.importorskip("tkinter", reason="Tkinter недоступен на этой платформе")

from texttospeech.app import build_window  # noqa: E402


@pytest.fixture
def root():
    window = build_window()
    yield window
    window.destroy()


def test_window_creates(root) -> None:
    assert root.title() == "TextToSpeech"
    assert root.winfo_exists() == 1


def _find_widgets(root, widget_type):
    """Ищет виджеты типа по всему дереву, а не только среди прямых потомков."""
    found = []
    for child in root.winfo_children():
        if isinstance(child, widget_type):
            found.append(child)
        found.extend(_find_widgets(child, widget_type))
    return found


def test_window_has_text_field(root) -> None:
    root.update_idletasks()

    texts = _find_widgets(root, tk.Text)
    assert texts, "в окне нет поля ввода текста"
    assert texts[0].get("1.0", "end").strip(), "поле ввода пустое"


def test_window_geometry(root) -> None:
    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()

    assert width >= 480, f"окно слишком узкое: {width}"
    assert height >= 400, f"окно слишком низкое: {height}"