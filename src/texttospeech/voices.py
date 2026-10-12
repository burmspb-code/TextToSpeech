"""Каталог голосов Piper и скачивание моделей.

Модель — обычный файл .onnx весом ~60 МБ. Интернет нужен только для
первоначального скачивания, дальше синтез работает полностью офлайн.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import requests

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Куда складываются скачанные модели.
VOICES_DIR = Path.home() / ".local" / "share" / "piper-voices"

ProgressCallback = Callable[[int, int], None]  # (скачано байт, всего байт)


@dataclass(frozen=True)
class Voice:
    """Голос Piper.

    key разбирается как <locale>-<name>-<quality>, например
    "ru_RU-dmitri-medium".
    """

    key: str
    title: str  # название для интерфейса
    gender: str  # "male" | "female"

    @property
    def locale(self) -> str:
        return self.key.rsplit("-", 2)[0]

    @property
    def name(self) -> str:
        """Имя голоса: "ru_RU-dmitri-medium" -> "dmitri"."""
        return self.key.rsplit("-", 2)[1]

    @property
    def quality(self) -> str:
        """Уровень качества: "ru_RU-dmitri-medium" -> "medium"."""
        return self.key.rsplit("-", 1)[1]

    @property
    def family(self) -> str:
        """Подкаталог на Hugging Face: ru или en."""
        return self.locale[:2]

    @property
    def filename(self) -> str:
        """Имя файла модели: ru_RU-dmitri-medium.onnx"""
        return f"{self.key}.onnx"

    @property
    def relative_path(self) -> str:
        """Путь модели: ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx"""
        return f"{self.family}/{self.locale}/{self.name}/{self.quality}/{self.filename}"

    @property
    def model_path(self) -> Path:
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
        return self.model_path.exists() and self.config_path.exists()

    @property
    def label(self) -> str:
        """Подпись для выпадающего списка."""
        flag = "RU" if self.locale.startswith("ru") else "EN"
        return f"{self.title} · {flag}"

    def missing_files(self) -> list[Path]:
        return [p for p in (self.config_path, self.model_path) if not p.exists()]


def _v(key: str, title: str, gender: str) -> Voice:
    return Voice(key=key, title=title, gender=gender)


# Каталог: только одноголосые модели уровня medium — они лучше всего
# звучат и при этом невелики (~60 МБ).
CATALOG: tuple[Voice, ...] = (
    # --- Русский ---
    _v("ru_RU-dmitri-medium", "Дмитрий", "male"),
    _v("ru_RU-denis-medium", "Денис", "male"),
    _v("ru_RU-ruslan-medium", "Руслан", "male"),
    _v("ru_RU-irina-medium", "Ирина", "female"),
    # --- Английский ---
    _v("en_US-amy-medium", "Amy", "female"),
    _v("en_US-ryan-medium", "Ryan", "male"),
    _v("en_US-lessac-medium", "Lessac", "female"),
    _v("en_US-sam-medium", "Sam", "male"),
    _v("en_US-kristin-medium", "Kristin", "female"),
    _v("en_US-kusal-medium", "Kusal", "male"),
    _v("en_US-joe-medium", "Joe", "male"),
    _v("en_US-john-medium", "John", "male"),
    _v("en_US-bryce-medium", "Bryce", "male"),
    _v("en_US-hfc_female-medium", "HFC Female", "female"),
    _v("en_US-hfc_male-medium", "HFC Male", "male"),
    # --- Британский английский ---
    _v("en_GB-alan-medium", "Alan", "male"),
    _v("en_GB-alba-medium", "Alba", "female"),
    _v("en_GB-cori-medium", "Cori", "female"),
    _v("en_GB-jenny_dioco-medium", "Jenny Dioco", "female"),
    _v("en_GB-northern_english_male-medium", "Northern Male", "male"),
)

DEFAULT_VOICE_KEY = "ru_RU-dmitri-medium"


def find_voice(key: str) -> Voice:
    """Возвращает голос по ключу. Бросает ValueError, если голоса нет."""
    for voice in CATALOG:
        if voice.key == key:
            return voice
    raise ValueError(f"Неизвестный голос: {key}")


def find_voice_by_label(label: str) -> Voice:
    """Возвращает голос по подписи из выпадающего списка."""
    for voice in CATALOG:
        if voice.label == label:
            return voice
    return find_voice(DEFAULT_VOICE_KEY)


def voice_size_mb(voice: Voice) -> float:
    """Размер модели в МБ. Для нескачанных — типичные ~60 МБ."""
    if voice.model_path.exists():
        return voice.model_path.stat().st_size / 1024 / 1024
    return 60.0


def voices_for_locale(prefix: str = "ru") -> tuple[Voice, ...]:
    """Голоса, подходящие для языка: "ru", "en" или "en_GB"."""
    return tuple(v for v in CATALOG if v.locale.lower().startswith(prefix.lower()))


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
    return (v for v in CATALOG if v.is_downloaded)