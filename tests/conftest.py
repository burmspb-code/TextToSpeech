"""Общие фикстуры для тестов Qt-интерфейса."""
import os

# Должно быть выставлено до импорта PyQt6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from texttospeech.app import TTSApp


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Одно QApplication на всю сессию тестов."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp: QApplication):
    """Окно приложения в оффскрин-режиме."""
    widget = TTSApp()
    widget.show()
    qapp.processEvents()
    # Чистое состояние, как у свежеоткрытого приложения.
    widget._set_text("")
    widget._set_dirty(False)
    yield widget
    # Тесты намеренно оставляют правки, поэтому закрываем без подтверждения.
    widget.dirty = False
    widget.close()
    widget.deleteLater()
    qapp.processEvents()
