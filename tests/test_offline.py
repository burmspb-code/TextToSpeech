"""Проверка: Piper работает БЕЗ интернета.

Блокируем любые сетевые вызовы на уровне socket и синтезируем речь.
Если синтез прошёл — движок и модель полностью офлайн, интернет нужен
только для первоначального скачивания голоса.

Тест требует скачанной модели. Чтобы её получить, сначала запустите
docs/compare_piper.py.
"""
import socket
import wave
from pathlib import Path

import pytest

VOICE = Path.home() / ".local/share/piper-voices/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"
TEXT = "Этот текст синтезируется без интернета."


class NetworkBlocked(RuntimeError):
    """Сработало, если кто-то попытался выйти в сеть."""


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перекрывает создание сокетов, DNS и подключений."""

    def blocked(*args, **kwargs):
        raise NetworkBlocked("синтез не должен требовать интернет")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.mark.skipif(not VOICE.exists(), reason="модель не скачана — запустите docs/compare_piper.py")
def test_synthesizes_without_network(no_network, tmp_path: Path) -> None:
    from piper import PiperVoice

    voice = PiperVoice.load(str(VOICE))
    dest = tmp_path / "offline.wav"

    with wave.open(str(dest), "wb") as w:
        voice.synthesize_wav(TEXT, w)

    assert dest.exists(), "аудиофайл не создан"
    assert dest.stat().st_size > 0, "аудиофайл пустой"

    with wave.open(str(dest)) as w:
        frames, rate = w.getnframes(), w.getframerate()

    duration = frames / rate
    assert 1.0 < duration < 20.0, f"подозрительная длительность: {duration:.2f} c"


def test_voice_model_is_local_file() -> None:
    """Модель голоса — обычный файл на диске, а не ссылка на сервис."""
    assert VOICE.suffix == ".onnx", "модель должна быть ONNX-файлом"
    assert VOICE.exists(), (
        f"модель не найдена: {VOICE}\n"
        f"Запустите docs/compare_piper.py, чтобы скачать её."
    )
    assert VOICE.stat().st_size > 10 * 1024 * 1024, "модель подозрительно маленькая"