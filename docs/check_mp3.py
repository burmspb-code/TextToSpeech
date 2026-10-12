"""Проверка MP3 без внешних зависимостей: заголовок и оценка длительности.

edge-tts отдаёт CBR 48 кбит/с, 24 кГц, моно — константы из пакета.
"""
import sys
from pathlib import Path

# Таблицы MPEG: [MPEG1, MPEG2] для каждого индекса частоты дискретизации.
RATES = {
    1: (32000, 16000),
    2: (44100, 22050),
    3: (48000, 24000),
}
BITRATES_V2_L3 = {1: 8, 2: 16, 3: 24, 4: 32, 5: 40, 6: 48, 7: 56, 8: 64, 9: 80, 10: 96, 11: 112, 12: 128, 13: 160, 14: 192}


def mp3_info(path: Path) -> str:
    data = path.read_bytes()
    if data[:3] == b"ID3":
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        offset, tag = 10 + size, "ID3v2"
    else:
        offset, tag = 0, "без тега"

    for i in range(offset, min(offset + 4096, len(data) - 4)):
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            version_id = (data[i + 1] >> 3) & 0x03
            if version_id == 1:  # зарезервировано
                continue
            version = "2" if version_id == 2 else "1"
            layer = {1: "III", 2: "II", 3: "I"}.get((data[i + 1] >> 1) & 0x03, "?")
            rate_idx = (data[i + 2] >> 2) & 0x03
            br_idx = (data[i + 2] >> 4) & 0x0F

            rates = RATES.get(rate_idx, (0, 0))
            sample_rate = rates[1] if version == "2" else rates[0]
            bitrate = BITRATES_V2_L3.get(br_idx, 0) * 1000 if layer == "III" else 0

            duration = path.stat().st_size * 8 / bitrate if bitrate else 0.0
            return (f"{tag}, MPEG{version} L{layer}, {sample_rate} Hz, "
                    f"{bitrate // 1000} кбит/с, ~{duration:.2f} c")

    return f"{tag}, MPEG-фрейм не найден — это не MP3"


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output")
    files = sorted(target.glob("*.mp3"))
    if not files:
        print("MP3-файлов нет")
    for p in files:
        print(f"{p.name:32s} {p.stat().st_size:>7} Б  {mp3_info(p)}")