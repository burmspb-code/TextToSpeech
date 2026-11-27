"""Тесты синтеза: движок, склейка аудио и полный путь через GUI."""
import io
import sys
import time
import types
import wave
import zipfile
from pathlib import Path
from typing import ClassVar

import pytest
from PyQt6.QtWidgets import QApplication

from texttospeech.app import TTSApp
from texttospeech.audio import (
    AudioFormatMismatch,
    Player,
    change_speed,
    concat_wavs,
    wav_duration,
)
from texttospeech.engines import PiperEngine, SileroEngine, split_text
from texttospeech.voices import (
    CATALOG,
    DEFAULT_SILERO_VOICE_KEY,
    PROJECT_ROOT,
    QUALITY_LEVELS,
    SILERO_CATALOG,
    SILERO_SAMPLE_RATES,
    SILERO_SPEAKERS,
    SPEAKERS,
    VOICES_DIR,
    download_silero_model,
    expose_silero_model,
    find_voice,
    find_voice_by_label,
    quality_label,
    quality_levels,
    silero_models_dir,
    voice_size_mb,
    voices_for_quality,
)

# Голос, который гарантированно скачан (его тянут тесты офлайна).
VOICE_KEY = "ru_RU-dmitri-medium"
pytestmark_audio = pytest.mark.skipif(
    not find_voice(VOICE_KEY).is_downloaded,
    reason="модель не скачана — запустите docs/compare_piper.py",
)
pytestmark_silero = pytest.mark.skipif(
    not find_voice(DEFAULT_SILERO_VOICE_KEY).is_downloaded,
    reason="модель Silero не скачана — нажмите «Озвучить» в приложении",
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


def test_catalog_is_russian_only() -> None:
    """Иностранные голоса удалены: в каталоге только ru_RU."""
    assert CATALOG
    assert {v.locale for v in CATALOG} == {"ru_RU"}
    assert {v.name for v in CATALOG} == {speaker.name for speaker in SPEAKERS}


def test_quality_levels_are_real() -> None:
    """У русских моделей Piper доступен только уровень medium."""
    assert QUALITY_LEVELS == ("medium",)
    assert quality_label("medium") == "Среднее (~60 МБ)"
    assert voices_for_quality("medium") == CATALOG
    assert all(v.quality == "medium" for v in CATALOG)


def test_silero_catalog_is_russian_and_multivoice() -> None:
    assert len(SILERO_CATALOG) == len(SILERO_SPEAKERS) * len(SILERO_SAMPLE_RATES)
    assert all(v.engine == "silero" and v.locale == "ru_RU" for v in SILERO_CATALOG)
    assert {v.name for v in SILERO_CATALOG} == {s.name for s in SILERO_SPEAKERS}
    assert {v.quality for v in SILERO_CATALOG} == {str(r) for r in SILERO_SAMPLE_RATES}


def test_silero_quality_levels() -> None:
    assert quality_levels("piper") == ("medium",)
    assert quality_levels("silero") == ("8000", "24000", "48000")
    assert quality_label("48000") == "48 кГц (высокое)"
    assert len(voices_for_quality("48000", "silero")) == len(SILERO_SPEAKERS)


def test_speakers_are_engine_specific() -> None:
    """Списки дикторов не совпадают — поиск ограничен выбранным движком."""
    piper = find_voice_by_label("Ирина", "medium", "piper")
    silero = find_voice_by_label("Ксения", "24000", "silero")
    assert piper.engine == "piper"
    assert silero.engine == "silero"
    # Ирины в модели Silero нет: подпись из другого движка не должна
    # незаметно подменить голос, а вернётся голос по умолчанию (xenia).
    assert find_voice_by_label("Ирина", "24000", "silero").engine == "silero"
    assert find_voice_by_label("Ирина", "24000", "silero").name == "xenia"


def test_find_voice_silero_key() -> None:
    voice = find_voice(DEFAULT_SILERO_VOICE_KEY)
    assert voice.is_silero
    assert voice.name == "xenia"
    assert voice.filename == f"{voice.model_id}_ru.pt"


def test_models_live_in_project_folder() -> None:
    """Модели обеих движков лежат в отдельной папке проекта."""
    assert VOICES_DIR == PROJECT_ROOT / "models" / "piper"
    assert silero_models_dir() == PROJECT_ROOT / "models" / "silero"

    piper = find_voice(VOICE_KEY)
    silero = find_voice(DEFAULT_SILERO_VOICE_KEY)
    assert piper.model_path == VOICES_DIR / piper.relative_path
    assert piper.config_path == VOICES_DIR / f"{piper.relative_path}.json"
    assert silero.model_path == silero_models_dir() / silero.filename


def test_expose_silero_model_links_project_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """silero-tts получает модель из папки проекта, а не из другой копии."""
    source_dir = tmp_path / "project"
    package_dir = tmp_path / "package"
    monkeypatch.setattr(
        "texttospeech.voices.silero_models_dir", lambda: source_dir
    )
    monkeypatch.setattr(
        "texttospeech.voices.silero_package_models_dir", lambda: package_dir
    )
    payload = _zip_bytes()
    voice = find_voice(DEFAULT_SILERO_VOICE_KEY)
    (source_dir / voice.filename).parent.mkdir(parents=True, exist_ok=True)
    (source_dir / voice.filename).write_bytes(payload)

    target = expose_silero_model(voice)

    assert target == package_dir / voice.filename
    assert target is not None and target.read_bytes() == payload

    # Битый файл в кэше пакета заменяется моделью из проекта. Хардлинк
    # делит inode с источником, поэтому сначала снимаем саму ссылку.
    target.unlink()
    target.write_bytes(b"broken")
    assert expose_silero_model(voice) == target
    assert target.read_bytes() == payload


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("model", "ok")
    return buffer.getvalue()


def test_corrupt_silero_model_is_not_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("texttospeech.voices.silero_models_dir", lambda: tmp_path)
    voice = find_voice(DEFAULT_SILERO_VOICE_KEY)

    voice.model_path.write_bytes(b"broken")
    assert not voice.is_downloaded
    assert voice.missing_files() == [voice.model_path]

    voice.model_path.write_bytes(_zip_bytes())
    assert voice.is_downloaded
    assert voice.missing_files() == []


def test_silero_download_replaces_corrupt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _zip_bytes()

    class FakeResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            yield payload[: len(payload) // 2]
            yield payload[len(payload) // 2 :]

    monkeypatch.setattr(
        "texttospeech.voices.requests.get", lambda *args, **kwargs: FakeResponse()
    )
    monkeypatch.setattr("texttospeech.voices.silero_models_dir", lambda: tmp_path)
    voice = find_voice(DEFAULT_SILERO_VOICE_KEY)
    voice.model_path.write_bytes(b"broken")
    progress: list[tuple[int, int]] = []

    path = download_silero_model(voice, progress=lambda done, total: progress.append((done, total)))

    assert path == voice.model_path
    assert path.read_bytes() == payload
    assert not path.with_suffix(path.suffix + ".part").exists()
    assert progress[-1] == (len(payload), len(payload))


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ru_RU-dmitri-medium", "ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"),
        ("ru_RU-irina-medium", "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"),
        ("ru_RU-denis-medium", "ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx"),
        ("ru_RU-ruslan-medium", "ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx"),
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


@pytest.mark.parametrize(
    ("speed", "expected"), [(2.0, 0.5), (0.5, 2.0), (1.0, 1.0)]
)
def test_change_speed_changes_duration(
    tmp_path: Path, speed: float, expected: float
) -> None:
    src = tmp_path / f"in_{speed}.wav"
    dest = tmp_path / f"out_{speed}.wav"
    _make_wav(src, 1.0)

    change_speed(src, dest, speed)

    assert wav_duration(dest) == pytest.approx(expected, abs=0.05)


def test_change_speed_keeps_pitch(tmp_path: Path) -> None:
    """Phase vocoder ускоряет речь, не поднимая тон на октаву."""
    import math

    import torch

    rate = 24000
    src = tmp_path / "tone.wav"
    dest = tmp_path / "tone_fast.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                int(12000 * math.sin(2 * math.pi * 440 * i / rate)).to_bytes(
                    2, "little", signed=True
                )
                for i in range(rate)
            )
        )

    change_speed(src, dest, 2.0)

    with wave.open(str(dest)) as w:
        frames = w.readframes(w.getnframes())
    samples = torch.frombuffer(bytearray(frames), dtype=torch.int16).float()
    spectrum = torch.abs(torch.fft.rfft(samples))
    peak_hz = int(torch.argmax(spectrum)) * rate / len(samples)
    assert abs(peak_hz - 440) < 25, f"тон сдвинулся: {peak_hz:.0f} Гц"


def test_player_available_on_windows() -> None:
    assert Player().available


# --- Движок ---

@pytestmark_audio
def test_engine_is_available() -> None:
    assert PiperEngine().is_available()


def test_silero_engine_is_available() -> None:
    assert SileroEngine().is_available()


def test_silero_availability_check_does_not_import_torch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_name: str):
        raise ImportError("нет пакета")

    monkeypatch.setattr(
        "texttospeech.engines.silero_engine.importlib.util.find_spec", broken
    )
    assert not SileroEngine().is_available()


def test_silero_prepare_downloads_with_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("texttospeech.voices.silero_models_dir", lambda: tmp_path)
    voice = find_voice(DEFAULT_SILERO_VOICE_KEY)
    calls: list[str] = []

    def fake_download(silero_voice, progress) -> Path:
        calls.append(f"download:{silero_voice.key}")
        assert progress is not None
        progress(5, 10)
        return tmp_path / silero_voice.filename

    monkeypatch.setattr(
        "texttospeech.engines.silero_engine.download_silero_model", fake_download
    )
    engine = SileroEngine()
    monkeypatch.setattr(engine, "_load", lambda v: calls.append(f"load:{v.key}"))

    engine.prepare(voice, on_progress=lambda done, total: None)

    assert calls == [f"download:{voice.key}", f"load:{voice.key}"]


def _fake_tts_class(
    instances: list[object],
    calls: list[tuple[str, int]],
    *,
    speakers: tuple[str, ...] = ("aidar", "eugene"),
    rates: tuple[int, ...] = (24000, 48000),
    empty: bool = False,
) -> type:
    class FakeTTS:
        def __init__(
            self, model_id: str, language: str, speaker: str, sample_rate: int
        ) -> None:
            self.model_id = model_id
            self.language = language
            self.speaker = speaker
            self.sample_rate = sample_rate
            instances.append(self)

        def get_available_speakers(self) -> list[str]:
            return list(speakers)

        def get_available_sample_rates(self) -> list[int]:
            return list(rates)

        def tts(self, _text: str, path: str) -> None:
            calls.append((self.speaker, self.sample_rate))
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.sample_rate)
                w.writeframes(b"" if empty else b"\x00\x00" * self.sample_rate)

    return FakeTTS


def _fake_silero_engine(
    monkeypatch: pytest.MonkeyPatch, tts_class: type
) -> SileroEngine:
    fake_module = types.ModuleType("silero_tts.silero_tts")
    fake_module.SileroTTS = tts_class  # type: ignore[attr-defined]
    parent = types.ModuleType("silero_tts")
    parent.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "silero_tts", parent)
    monkeypatch.setitem(sys.modules, "silero_tts.silero_tts", fake_module)

    monkeypatch.setattr(
        "texttospeech.engines.silero_engine.expose_silero_model", lambda voice: None
    )
    engine = SileroEngine()
    monkeypatch.setattr(engine, "is_available", lambda: True)
    return engine


def test_silero_reuses_model_and_applies_speed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Все дикторы делят одну модель; скорость меняется без сдвига тона."""
    instances: list[object] = []
    calls: list[tuple[str, int]] = []
    engine = _fake_silero_engine(
        monkeypatch, _fake_tts_class(instances, calls)
    )
    aidar = find_voice("silero-v5_5_ru-aidar-24000")
    eugene = find_voice("silero-v5_5_ru-eugene-48000")

    engine.synthesize("Привет", aidar, tmp_path / "aidar.wav")
    result = engine.synthesize("Мир", eugene, tmp_path / "eugene.wav", speed=2.0)

    assert len(instances) == 1, "модель загружена несколько раз"
    assert calls == [("aidar", 24000), ("eugene", 48000)]
    assert result.duration == pytest.approx(0.5, abs=0.05)
    assert not (tmp_path / "eugene.raw.wav").exists()


def test_silero_rejects_unknown_speaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Несуществующий диктор не должен превращаться в тишину."""
    engine = _fake_silero_engine(
        monkeypatch,
        _fake_tts_class([], [], speakers=("baya",)),
    )
    voice = find_voice("silero-v5_5_ru-aidar-24000")

    with pytest.raises(ValueError, match="отсутствует"):
        engine.synthesize("Привет", voice, tmp_path / "bad.wav")


def test_silero_empty_audio_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """silero-tts пишет пустой WAV вместо исключения — ловим это сами."""
    engine = _fake_silero_engine(
        monkeypatch, _fake_tts_class([], [], empty=True)
    )
    voice = find_voice("silero-v5_5_ru-aidar-24000")

    with pytest.raises(RuntimeError, match="не создал звук"):
        engine.synthesize("Привет", voice, tmp_path / "empty.wav")


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
def test_gui_synthesize_flow(window: TTSApp, tmp_path: Path) -> None:
    """Файл → кнопка «Озвучить» → готовый WAV.

    Синтез идёт в отдельном потоке, поэтому крутим цикл событий Qt,
    пока приложение не перестанет быть занятым.
    """
    window.output_dir = tmp_path
    window.engine_box.setCurrentText("Piper")

    source = tmp_path / "text.txt"
    source.write_text("Привет! Это проверка полного пути.", encoding="utf-8")
    window._load_path(source)

    window.on_synthesize()
    assert window.busy, "синтез должен запуститься в фоне"

    deadline = time.monotonic() + 120
    while window.busy and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)

    assert not window.busy, "синтез не завершился за отведённое время"
    assert window.last_audio is not None, "файл не создан"
    assert window.last_audio.exists()
    assert window.last_audio.stat().st_size > 0


@pytest.mark.slow
@pytestmark_silero
def test_gui_synthesize_flow_silero(window: TTSApp, tmp_path: Path) -> None:
    """Тот же путь через GUI, но с выбранным движком Silero."""
    window.output_dir = tmp_path
    window.engine_box.setCurrentText("Silero")

    source = tmp_path / "silero.txt"
    source.write_text("Привет! Это проверка Silero через интерфейс.", encoding="utf-8")
    window._load_path(source)
    window.on_synthesize()
    assert window.busy

    deadline = time.monotonic() + 120
    while window.busy and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)

    assert not window.busy, window.status_label.text()
    assert window.last_audio is not None
    assert window.last_audio.exists()
    assert wav_duration(window.last_audio) > 0.5

