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


def change_speed(src: Path, dest: Path, speed: float) -> None:
    """Меняет скорость моно WAV без сдвига высоты тона (phase vocoder).

    У Piper скорость — параметр модели, а API Silero её не поддерживает.
    Здесь скорость применяется к готовому звуку через STFT/ISTFT, поэтому
    речь ускоряется, оставаясь узнаваемой.
    """
    if speed <= 0:
        raise ValueError("скорость должна быть положительной")
    if abs(speed - 1.0) < 1e-6:
        if src != dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        return

    import torch
    import torchaudio.functional as AF

    with wave.open(str(src), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())

    if channels != 1 or width != 2:
        raise AudioFormatMismatch("изменение скорости поддерживает только моно 16-bit WAV")

    samples = torch.frombuffer(bytearray(raw), dtype=torch.int16).float() / 32768.0
    samples = samples.unsqueeze(0)  # STFT ожидает [каналы, сэмплы]
    n_fft = 512
    hop = n_fft // 4
    window = torch.hann_window(n_fft)
    spec = torch.stft(
        samples, n_fft=n_fft, hop_length=hop, window=window, return_complex=True
    )
    # В torchaudio 2.x вместо n_fft передаётся ожидаемый сдвиг фазы.
    phase_advance = torch.linspace(
        0, 3.141592653589793 * hop, spec.shape[-2]
    ).unsqueeze(-1)
    stretched = AF.phase_vocoder(spec, speed, phase_advance)
    out = torch.istft(
        stretched,
        n_fft=n_fft,
        hop_length=hop,
        window=window,
        length=max(1, int(samples.numel() / speed)),
    ).squeeze(0)
    pcm = (out.clamp(-1.0, 1.0) * 32767).to(torch.int16).numpy().tobytes()

    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)


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