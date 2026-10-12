"""Работа с аудиофайлами: склейка фрагментов и воспроизведение."""
import wave
from pathlib import Path


class AudioFormatMismatch(RuntimeError):
    """Фрагменты в разном формате — склеить их нельзя."""


def wav_info(path: Path) -> tuple[int, int, int]:
    """Возвращает (частота, каналы, бит на сэмпл) WAV-файла."""
    with wave.open(str(path), "rb") as wav:
        return wav.getframerate(), wav.getnchannels(), wav.getsampwidth()


def wav_duration(path: Path) -> float:
    """Длительность WAV-файла в секундах."""
    with wave.open(str(path), "rb") as wav:
        if wav.getnframes() == 0:
            return 0.0
        return wav.getnframes() / wav.getframerate()


def concat_wavs(parts: list[Path], dest: Path) -> float:
    """Склеивает WAV-фрагменты в один файл. Возвращает длительность."""
    if not parts:
        raise ValueError("Нет ни одного фрагмента для склейки")

    base = wav_info(parts[0])
    frames = bytearray()

    with wave.open(str(parts[0]), "rb") as wav:
        frames.extend(wav.readframes(wav.getnframes()))

    for part in parts[1:]:
        if wav_info(part) != base:
            raise AudioFormatMismatch(
                f"Формат {part.name} отличается от {parts[0].name}"
            )
        with wave.open(str(part), "rb") as wav:
            frames.extend(wav.readframes(wav.getnframes()))

    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(base[1])
        out.setsampwidth(base[2])
        out.setframerate(base[0])
        out.writeframes(bytes(frames))

    return wav_duration(dest)


class Player:
    """Воспроизведение WAV средствами Windows.

    Библиотека playsound не нужна: winsound входит в стандартную
    поставку Python и умеет проигрывать WAV асинхронно.
    """

    def __init__(self) -> None:
        self._available = self._detect()
        self._current: Path | None = None

    @staticmethod
    def _detect() -> bool:
        try:
            import winsound  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_playing(self) -> bool:
        return self._current is not None

    def play(self, path: Path) -> bool:
        """Запускает воспроизведение. Возвращает False, если нечем играть."""
        if not self._available:
            return False

        import winsound

        self.stop()
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC,
        )
        self._current = path
        return True

    def stop(self) -> None:
        if not self._available:
            return
        import winsound

        try:
            winsound.PlaySound(None, 0)
        except RuntimeError:
            pass
        self._current = None