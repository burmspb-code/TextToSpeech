"""Каталог русских голосов Piper и Silero, скачивание моделей.

У Piper модель — файл .onnx ~60 МБ, у Silero — .pt ~140 МБ. Все модели
лежат в отдельной папке проекта ``models/`` (piper/ и silero/), а не в
домашнем каталоге или внутри site-packages. Интернет нужен только для
первоначального скачивания, дальше синтез работает полностью офлайн.

В официальном репозитории piper-voices для русского языка доступны только
четыре диктора и только уровень качества medium. У Silero качество — это
частота дискретизации: 8, 24 или 48 кГц (есть в конфиге моделей).
Селектор качества показывает реально существующие варианты.
"""
import importlib.util
import os
import shutil
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import requests

from .paths import PROJECT_ROOT

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Все скачанные модели лежат в отдельной папке проекта и не зависят
# от домашнего каталога пользователя.
MODELS_DIR = PROJECT_ROOT / "models"
VOICES_DIR = MODELS_DIR / "piper"
SILERO_MODELS_DIR = MODELS_DIR / "silero"

# Адрес моделей silero-tts из latest_silero_models.yml.
SILERO_MODEL_URL = "https://models.silero.ai/models/tts/ru/{model_id}.pt"


def silero_models_dir() -> Path:
    """Папка моделей Silero внутри проекта."""
    return SILERO_MODELS_DIR


def silero_package_models_dir() -> Path:
    """Куда silero-tts смотрит за моделью внутри установленного пакета.

    Путь жёстко задан в ``silero_tts.silero_tts`` через ``__file__``, поэтому
    готовую модель из проекта нужно «подключить» к этому каталогу.
    """
    spec = importlib.util.find_spec("silero_tts")
    if spec is not None and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            return Path(location) / "silero_models"
    return silero_models_dir()


def expose_silero_model(voice: Voice) -> Path | None:
    """Делает модель из ``models/silero`` видимой для silero-tts.

    Пакет ищет .pt только в своём каталоге ``silero_models``. Хардлинк
    (или копия, если файловая система его не поддерживает) позволяет
    библиотеке загружать модель из папки проекта без второй копии на диске.
    """
    if not voice.is_silero:
        raise ValueError("это не голос Silero")
    if not voice.is_downloaded:
        return None

    source = voice.model_path
    target_dir = silero_package_models_dir()
    if target_dir.resolve() == source.parent.resolve():
        return source

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / voice.filename
    if target.exists():
        try:
            if os.path.samefile(source, target):
                return target
        except OSError:
            pass

    target_valid = (
        target.exists()
        and target.is_file()
        and zipfile.is_zipfile(target)
        and target.stat().st_size == source.stat().st_size
    )
    temp = target.with_name(f"{target.name}.link")
    temp.unlink(missing_ok=True)
    try:
        os.link(source, temp)
    except OSError:
        if target_valid:
            # Хардлинки не поддерживаются, но рабочая копия уже есть.
            return target
        shutil.copy2(source, temp)

    try:
        temp.replace(target)
    except OSError:
        # Файл может быть открыт работающим приложением. Корректную копию
        # того же размера оставляем: следующий запуск попробует снова.
        temp.unlink(missing_ok=True)
        if target_valid:
            return target
        raise
    return target


ProgressCallback = Callable[[int, int], None]  # (скачано байт, всего байт)


@dataclass(frozen=True)
class Voice:
    """Голос одного из двух движков.

    У Piper key выглядит как "ru_RU-dmitri-medium", у Silero —
    "silero-v5_5_ru-aidar-24000" (движок-модель-диктор-частота).
    """

    key: str
    title: str  # название для интерфейса
    gender: str  # "male" | "female"
    engine: str = "piper"
    model_id: str = ""  # только Silero
    speaker: str = ""  # только Silero
    sample_rate: int = 0  # только Silero, качество

    @property
    def is_silero(self) -> bool:
        return self.engine == "silero"

    @property
    def locale(self) -> str:
        return "ru_RU" if self.is_silero else self.key.rsplit("-", 2)[0]

    @property
    def name(self) -> str:
        """Имя диктора без движка и качества."""
        return self.speaker if self.is_silero else self.key.rsplit("-", 2)[1]

    @property
    def quality(self) -> str:
        """У Piper — medium, у Silero — частота дискретизации."""
        if self.is_silero:
            return str(self.sample_rate)
        return self.key.rsplit("-", 1)[1]

    @property
    def family(self) -> str:
        """Подкаталог на Hugging Face: ru или en."""
        return self.locale[:2]

    @property
    def filename(self) -> str:
        """Имя файла модели: .onnx у Piper, .pt у Silero."""
        if self.is_silero:
            return f"{self.model_id}_ru.pt"
        return f"{self.key}.onnx"

    @property
    def relative_path(self) -> str:
        """Путь модели в хранилище (только для Piper/Hugging Face)."""
        return f"{self.family}/{self.locale}/{self.name}/{self.quality}/{self.filename}"

    @property
    def model_path(self) -> Path:
        if self.is_silero:
            return silero_models_dir() / self.filename
        return VOICES_DIR / self.relative_path

    @property
    def config_path(self) -> Path:
        stem = f"{self.family}/{self.locale}/{self.name}/{self.quality}/{self.filename}"
        return VOICES_DIR / f"{stem}.json"

    @property
    def url(self) -> str:
        return f"{HF_BASE}/{self.relative_path}"

    @property
    def config_url(self) -> str:
        return f"{self.url}.json"

    @property
    def is_downloaded(self) -> bool:
        if self.is_silero:
            # .pt — torch.package (zip). Простое exists() принимало бы
            # оборванную загрузку за готовую модель.
            return self.model_path.exists() and zipfile.is_zipfile(self.model_path)
        return self.model_path.exists() and self.config_path.exists()

    @property
    def label(self) -> str:
        """Подпись для выпадающего списка. Все голоса русские — флаг не нужен."""
        return self.title

    def missing_files(self) -> list[Path]:
        if self.is_silero:
            return [] if self.is_downloaded else [self.model_path]
        return [p for p in (self.config_path, self.model_path) if not p.exists()]


@dataclass(frozen=True)
class Speaker:
    """Русский диктор: имя в ключе модели и подпись в интерфейсе."""

    name: str
    title: str
    gender: str


# Только русские дикторы из ru/ru_RU репозитория piper-voices.
SPEAKERS: tuple[Speaker, ...] = (
    Speaker("dmitri", "Дмитрий", "male"),
    Speaker("denis", "Денис", "male"),
    Speaker("ruslan", "Руслан", "male"),
    Speaker("irina", "Ирина", "female"),
)

# Уровни качества, которые реально есть для русских моделей. Для ru_RU
# существуют только каталоги medium — low/high на Hugging Face дают 404.
QUALITY_LEVELS: tuple[str, ...] = ("medium",)
QUALITY_LABELS: dict[str, str] = {"medium": "Среднее (~60 МБ)"}
DEFAULT_QUALITY = "medium"


def _voice(speaker: Speaker, quality: str) -> Voice:
    return Voice(
        key=f"ru_RU-{speaker.name}-{quality}",
        title=speaker.title,
        gender=speaker.gender,
    )


CATALOG: tuple[Voice, ...] = tuple(
    _voice(speaker, quality)
    for quality in QUALITY_LEVELS
    for speaker in SPEAKERS
)

DEFAULT_VOICE_KEY = f"ru_RU-{SPEAKERS[0].name}-{DEFAULT_QUALITY}"

# --- Silero ---
# Модель v5_5_ru — русская, multi-speaker. Качество задаётся частотой
# дискретизации: все три значения есть в latest_silero_models.yml.
SILERO_MODEL_ID = "v5_5_ru"
# Реальный список модели v5_5_ru: aidar, baya, kseniya, eugene, xenia.
# kseniya и xenia — разные дикторы, поэтому подписи различаем.
SILERO_SPEAKERS: tuple[Speaker, ...] = (
    Speaker("aidar", "Айдар", "male"),
    Speaker("baya", "Бая", "female"),
    Speaker("kseniya", "Ксения", "female"),
    Speaker("eugene", "Евгений", "male"),
    Speaker("xenia", "Ксения (xenia)", "female"),
)
SILERO_SAMPLE_RATES = (8000, 24000, 48000)
DEFAULT_SILERO_QUALITY = "48000"


def _silero_voice(speaker: Speaker, rate: int) -> Voice:
    return Voice(
        key=f"silero-{SILERO_MODEL_ID}-{speaker.name}-{rate}",
        title=speaker.title,
        gender=speaker.gender,
        engine="silero",
        model_id=SILERO_MODEL_ID,
        speaker=speaker.name,
        sample_rate=rate,
    )


SILERO_CATALOG: tuple[Voice, ...] = tuple(
    _silero_voice(speaker, rate)
    for rate in SILERO_SAMPLE_RATES
    for speaker in SILERO_SPEAKERS
)
# Ксения в варианте xenia — голос по умолчанию для Silero.
DEFAULT_SILERO_SPEAKER = "xenia"
DEFAULT_SILERO_VOICE_KEY = (
    f"silero-{SILERO_MODEL_ID}-{DEFAULT_SILERO_SPEAKER}-{DEFAULT_SILERO_QUALITY}"
)

ALL_VOICES: tuple[Voice, ...] = CATALOG + SILERO_CATALOG

QUALITY_LEVELS_BY_ENGINE: dict[str, tuple[str, ...]] = {
    "piper": QUALITY_LEVELS,
    "silero": tuple(str(rate) for rate in SILERO_SAMPLE_RATES),
}
QUALITY_LABELS.update(
    {
        "8000": "8 кГц (низкое)",
        "24000": "24 кГц (среднее)",
        "48000": "48 кГц (высокое)",
    }
)
DEFAULT_QUALITY_BY_ENGINE: dict[str, str] = {
    "piper": DEFAULT_QUALITY,
    "silero": DEFAULT_SILERO_QUALITY,
}
DEFAULT_VOICE_BY_ENGINE: dict[str, str] = {
    "piper": DEFAULT_VOICE_KEY,
    "silero": DEFAULT_SILERO_VOICE_KEY,
}


def quality_levels(engine: str) -> tuple[str, ...]:
    """Реальные уровни качества для выбранного движка."""
    return QUALITY_LEVELS_BY_ENGINE.get(engine, QUALITY_LEVELS)


def find_voice(key: str) -> Voice:
    """Возвращает голос по ключу. Бросает ValueError, если голоса нет."""
    for voice in ALL_VOICES:
        if voice.key == key:
            return voice
    raise ValueError(f"Неизвестный голос: {key}")


def find_voice_by_label(
    label: str, quality: str | None = None, engine: str | None = None
) -> Voice:
    """Возвращает голос по подписи из выпадающего списка."""
    for voice in ALL_VOICES:
        if (
            voice.label == label
            and (quality is None or voice.quality == quality)
            and (engine is None or voice.engine == engine)
        ):
            return voice
    default = DEFAULT_VOICE_BY_ENGINE.get(engine or "piper", DEFAULT_VOICE_KEY)
    return find_voice(default)


def voices_for_quality(quality: str, engine: str = "piper") -> tuple[Voice, ...]:
    """Дикторы, доступные на выбранном уровне качества."""
    return tuple(
        v
        for v in ALL_VOICES
        if v.quality == quality and v.engine == engine
    )


def quality_label(quality: str) -> str:
    """Подпись уровня качества для интерфейса."""
    return QUALITY_LABELS.get(quality, quality)


def voice_size_mb(voice: Voice) -> float:
    """Размер модели в МБ. Для нескачанных — типичный для движка."""
    if voice.is_downloaded:
        return voice.model_path.stat().st_size / 1024 / 1024
    return 140.0 if voice.is_silero else 60.0


def voices_for_locale(prefix: str = "ru") -> tuple[Voice, ...]:
    """Голоса для языкового префикса (в каталоге только "ru")."""
    return tuple(v for v in ALL_VOICES if v.locale.lower().startswith(prefix.lower()))


def download_silero_model(
    voice: Voice,
    progress: ProgressCallback | None = None,
    timeout: int = 60,
    attempts: int = 3,
) -> Path:
    """Скачивает .pt-модель Silero в ``models/silero``, если её нет или она бита.

    Пишем во временный файл и проверяем zip-структуру torch.package:
    оборванная загрузка никогда не становится «готовой» моделью. При обрыве
    продолжаем с того же места. Видимость для silero-tts обеспечивает
    ``expose_silero_model`` — сам пакет в папку проекта не пишет.
    """
    if not voice.is_silero:
        raise ValueError("это не голос Silero")

    path = voice.model_path
    if path.exists() and zipfile.is_zipfile(path):
        return path
    if path.exists():
        path.unlink()  # битый файл от предыдущей загрузки

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    url = SILERO_MODEL_URL.format(model_id=voice.model_id)

    print(f"Скачиваю {voice.title}: {path.name}")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        start = temp.stat().st_size if temp.exists() else 0
        headers = {"Range": f"bytes={start}-"} if start else None
        try:
            with requests.get(
                url, stream=True, timeout=timeout, headers=headers
            ) as response:
                if start and response.status_code == 416:
                    temp.unlink(missing_ok=True)
                    raise requests.RequestException("сервер отклонил докачку")
                response.raise_for_status()
                if start and response.status_code != 206:
                    # Range проигнорирован — сервер отдал файл целиком.
                    start = 0

                remaining = int(response.headers.get("Content-Length", 0))
                total = start + remaining if remaining else 0
                mode = "ab" if start else "wb"
                with temp.open(mode) as fh:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        start += len(chunk)
                        if progress:
                            progress(start, total)

            if zipfile.is_zipfile(temp):
                temp.replace(path)
                print(f"  готово: {_human_size(path.stat().st_size)}")
                return path
            last_error = RuntimeError("загруженный файл не является моделью")
        except requests.RequestException as exc:
            last_error = exc
            print(f"  попытка {attempt}: {exc}")

    raise RuntimeError(f"Не удалось скачать модель Silero: {last_error}") from last_error


def _human_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("Б", "КБ", "МБ"):
        if size < 1024 or unit == "МБ":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} МБ"


def download_voice(
    voice: Voice,
    progress: ProgressCallback | None = None,
    timeout: int = 600,
) -> Path:
    """Скачивает модель голоса, если её ещё нет. Возвращает путь к .onnx.

    Файл скачивается во временную папку и только потом переименовывается:
    оборванная загрузка не оставит «половинчатую» модель, которую потом
    пришлось бы проверять вручную.
    """
    for path, url in (
        (voice.config_path, voice.config_url),
        (voice.model_path, voice.url),
    ):
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")

        print(f"Скачиваю {voice.title}: {path.name}")
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            with temp.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        temp.replace(path)
        print(f"  готово: {_human_size(path.stat().st_size)}")

    return voice.model_path


def iter_downloaded() -> Iterator[Voice]:
    """Голоса, уже скачанные на диск."""
    return (v for v in ALL_VOICES if v.is_downloaded)