"""Проверки журнала: один файл с перезаписью по лимиту."""
from pathlib import Path

from texttospeech.logging_setup import setup_log_file


def test_log_file_stays_within_limit(tmp_path: Path) -> None:
    """Достигли лимита — старые строки стираются, файл один."""
    path = tmp_path / "texttospeech.log"
    log = setup_log_file(path, limit=20)

    log.write("0123456789")
    log.write("0123456789")
    assert path.read_text(encoding="utf-8") == "0123456789" * 2

    log.write("abcdef")
    assert path.read_text(encoding="utf-8") == "abcdef"
    assert list(tmp_path.iterdir()) == [path]

    log.close()


def test_log_file_is_rewritten_on_start(tmp_path: Path) -> None:
    """Каждый запуск начинает журнал заново, без архивов."""
    path = tmp_path / "texttospeech.log"
    path.write_text("старый запуск\n", encoding="utf-8")

    log = setup_log_file(path)
    assert path.read_text(encoding="utf-8") == ""

    log.write("новый запуск\n")
    assert path.read_text(encoding="utf-8") == "новый запуск\n"
    assert list(tmp_path.iterdir()) == [path]

    log.close()
