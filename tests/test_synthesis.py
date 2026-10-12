"""Тесты синтеза: движок, склейка аудио и полный путь через GUI."""
import threading
import tkinter as tk
import wave
from pathlib import Path

import pytest

pytest.importorskip("tkinter", reason="Tkinter недоступен")

from texttospeech.audio import (  # noqa: E402
    AudioFormatMismatch,
    Player,
    concat_wavs,
    wav_duration,
)
from texttospeech.engines import PiperEngine, split_text  # noqa: E402
from texttospeech.voices import (  # noqa: E402
    CATALOG,
    find_voice,
    find_voice_by_label,
    voice_size_mb,
)

# Голос, который гарантированно скачан (его тянут тесты офлайна).
VOICE_KEY = "ru_RU-dmitri-medium"
pytestmark_audio = pytest.mark.skipif(
    not find_voice(VOICE_KEY).is_downloaded,
    reason="модель не скачана — запустите docs/compare_piper.py",
)


# --- Каталог голосов ---

def test_catalog_not_empty() -> None:
    assert len(CATALOG) > 0


def test_voice_keys_unique() -> None:
    keys = [v.key for v in CATALOG]
    assert len(keys) == len(set(keys)), "в каталоге есть повторяющиеся ключи"


def test_voice_labels_unique() -> None:
    """Подписи идут в выпадающий список — они должны различаться."""
    labels = [v.label for v in CATALOG]
    assert len(labels) == len(set(labels)), "две подписи совпали, выбор голоса сломается"


def test_voice_has_ru_and_en() -> None:
    locales = {v.locale for v in CATALOG}
    assert any(loc.startswith("ru") for loc in locales), "нет русских голосов"
    assert any(loc.startswith("en") for loc in locales), "нет английских голосов"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ru_RU-dmitri-medium", "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"),
        ("en_US-ryan-medium", "en/en_US/ryan/medium/en_US-ryan-medium.onnx"),
        ("en_GB-alan-medium", "en/en_GB/alan/medium/en_GB-alan-medium.onnx"),
    ],
)
def test_relative_path(key: str, expected: str) -> None:
    """Путь должен совпадать со структурой репозитория голосов на Hugging Face."""
    assert find_voice(key).relative_path == expected


def test_voice_parts() -> None:
    voice = find_voice("ru_RU-dmitri-medium")
    assert voice.locale == "ru_RU"
    assert voice.name == "dmitri"
    assert voice.quality == "medium"
    assert voice.family == "ru"


def test_find_voice_unknown() -> None:
    with pytest.raises(ValueError, match="Неизвестный голос"):
        find_voice("xx_XX-nobody-medium")


def test_find_voice_by_label() -> None:
    voice = find_voice(VOICE_KEY)
    assert find_voice_by_label(voice.label) == voice


def test_find_voice_by_label_falls_back() -> None:
    """Неизвестная подпись не должна ронять программу."""
    assert find_voice_by_label("ерунда").key == VOICE_KEY


def test_voice_size_mb() -> None:
    assert voice_size_mb(find_voice(VOICE_KEY)) > 10.0


# --- Деление текста ---

def test_split_empty() -> None:
    assert split_text("") == []
    assert split_text("   \n  ") == []


def test_split_short_single_chunk() -> None:
    assert len(split_text("Привет. Как дела?")) == 1


def test_split_respects_limit() -> None:
    text = "Это предложение. " * 200
    for chunk in split_text(text, limit=200):
        assert len(chunk) <= 200


def test_split_long_word_sentence() -> None:
    """Предложение длиннее лимита режется по словам, а не теряется."""
    text = "слово " * 400
    parts = split_text(text, limit=100)
    assert len(parts) > 1
    assert all(len(p) <= 100 for p in parts)


def test_split_keeps_paragraphs_separate() -> None:
    parts = split_text("Первый абзац.\n\nВторой абзац.")
    assert len(parts) == 2


def test_split_keeps_all_words() -> None:
    """Ни одно слово не должно потеряться при делении."""
    text = "Раз два три. Четыре пять шесть."
    joined = " ".join(" ".join(split_text(text)).split())
    assert joined == " ".join(text.split())


# --- Склейка аудио ---

def _make_wav(path: Path, seconds: float, rate: int = 22050) -> None:
    import struct

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(10000 * ((i % 100) / 100 - 0.5)))
            for i in range(int(rate * seconds))
        )
        w.writeframes(frames)


def test_concat_wavs(tmp_path: Path) -> None:
    parts = []
    for i in range(3):
        p = tmp_path / f"p{i}.wav"
        _make_wav(p, 0.5)
        parts.append(p)

    dest = tmp_path / "joined.wav"
    duration = concat_wavs(parts, dest)

    assert dest.exists()
    assert duration == pytest.approx(1.5, abs=0.05)
    assert wav_duration(dest) == pytest.approx(1.5, abs=0.05)


def test_concat_single_part(tmp_path: Path) -> None:
    p = tmp_path / "one.wav"
    _make_wav(p, 0.3)
    dest = tmp_path / "out.wav"

    assert concat_wavs([p], dest) == pytest.approx(0.3, abs=0.05)


def test_concat_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        concat_wavs([], tmp_path / "x.wav")


def test_concat_mismatched_formats(tmp_path: Path) -> None:
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _make_wav(a, 0.2, rate=22050)
    _make_wav(b, 0.2, rate=16000)

    with pytest.raises(AudioFormatMismatch):
        concat_wavs([a, b], tmp_path / "out.wav")


def test_player_available_on_windows() -> None:
    assert Player().available


# --- Движок ---

@pytestmark_audio
def test_engine_is_available() -> None:
    assert PiperEngine().is_available()


@pytestmark_audio
def test_engine_synthesizes(tmp_path: Path) -> None:
    voice = find_voice(VOICE_KEY)
    dest = tmp_path / "out.wav"

    result = PiperEngine().synthesize("Привет, это тест.", voice, dest)

    assert dest.exists()
    assert result.duration > 0.5
    assert result.audio_seconds > 0


@pytestmark_audio
def test_engine_speed_changes_duration(tmp_path: Path) -> None:
    """Быстрее — значит короче по времени."""
    voice = find_voice(VOICE_KEY)
    engine = PiperEngine()
    text = "Проверка влияния скорости на длительность."

    normal = engine.synthesize(text, voice, tmp_path / "n.wav", speed=1.0)
    fast = engine.synthesize(text, voice, tmp_path / "f.wav", speed=2.0)

    assert fast.duration < normal.duration, (
        f"speed=2.0 дал {fast.duration:.2f} c, speed=1.0 — {normal.duration:.2f} c"
    )


@pytestmark_audio
def test_engine_output_is_valid_wav(tmp_path: Path) -> None:
    voice = find_voice(VOICE_KEY)
    dest = tmp_path / "out.wav"

    PiperEngine().synthesize("Тест формата.", voice, dest)

    with wave.open(str(dest)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() > 8000


# --- Полный путь через GUI ---

@pytest.mark.slow
@pytestmark_audio
def test_gui_synthesize_flow(tmp_path: Path, monkeypatch) -> None:
    """Файл → кнопка «Озвучить» → готовый WAV.

    Синтез идёт в отдельном потоке, поэтому ждём результата в цикле,
    пока держим цикл событий Tkinter.
    """
    import texttospeech.app as app_module

    monkeypatch.setattr(app_module, "OUTPUT_DIR", tmp_path)

    root = tk.Tk()
    app = app_module.TTSApp(root)

    source = tmp_path / "text.txt"
    source.write_text("Привет! Это проверка полного пути.", encoding="utf-8")
    app._load_path(source)

    app.on_synthesize()
    assert app.busy, "синтез должен запуститься в фоне"

    deadline = threading.Event()
    steps = 0
    while app.busy and steps < 2000:
        root.update()
        steps += 1
        deadline.wait(0.01)

    assert not app.busy, "синтез не завершился за отведённое время"
    assert app.last_audio is not None, "файл не создан"
    assert app.last_audio.exists()
    assert app.last_audio.stat().st_size > 0

    root.destroy()