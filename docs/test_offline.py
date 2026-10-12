"""Проверка: работает ли Piper БЕЗ интернета.

Блокируем любые сетевые соединения на уровне socket и синтезируем речь.
Если синтез пройдёт — движок и модель полностью офлайн.
"""
import socket
import sys
import wave
from pathlib import Path

CACHE = Path.home() / ".local/share/piper-voices/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"
OUT = Path(r"C:\My_projects\TextToSpeech\output\offline_test_ru.wav")


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("Сеть заблокирована: синтез не должен требовать интернет")


def main() -> None:
    # Перекрываем создание любых сокетов — и IPv4, и IPv6.
    socket.socket = _blocked            # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    socket.getaddrinfo = _blocked        # type: ignore[assignment]

    from piper import PiperVoice

    print(f"модель на диске : {CACHE}")
    print(f"размер          : {CACHE.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"сеть            : ЗАБЛОКИРОВАНА")
    print("-" * 50)

    voice = PiperVoice.load(str(CACHE))
    with wave.open(str(OUT), "wb") as w:
        voice.synthesize_wav("Этот текст синтезируется без интернета.", w)

    print(f"[OK] синтез без сети прошёл -> {OUT}")
    print(f"размер файла    : {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    try:
        main()
    except NetworkBlocked as e:
        print(f"[FAIL] потребовалась сеть: {e}")
        sys.exit(1)