"""Пример: edge-tts (онлайн, Microsoft Edge).

Даёт лучшее качество речи, но требует интернет и иногда падает с
NoAudioReceived — сервер открывает соединение и закрывает его без
аудио. Сбой нерегулярный: бывает три раза подряд, бывает не
встречается вообще. Поэтому в приложении это запасной движок,
а основной — Piper.

Установка: poetry install --with edge
"""
import asyncio

import edge_tts

from _common import ensure_output_dir

CASES = [
    ("ru-RU-DmitryNeural", "Привет! Это проверка русского голоса."),
    ("ru-RU-SvetlanaNeural", "Привет! Это проверка женского голоса."),
    ("en-GB-RyanNeural", "Hello! This is an English voice check."),
]


async def main() -> None:
    out_dir = ensure_output_dir()

    for name, text in CASES:
        dest = out_dir / f"edge_{name}.mp3"
        comm = edge_tts.Communicate(text, name)
        try:
            await comm.save(str(dest))
        except edge_tts.exceptions.NoAudioReceived:
            print(f"[RETRY] {name}: сервер не вернул аудио — попробуйте ещё раз")
            continue
        print(f"[OK] {name} -> {dest}")


if __name__ == "__main__":
    asyncio.run(main())