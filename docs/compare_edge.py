"""Пример 1: edge-tts (онлайн, Microsoft Edge)."""
import asyncio
import edge_tts

TEXT_RU = "Привет! Это проверка русского голоса в приложении."
TEXT_EN = "Hello! This is an English voice check."


async def main() -> None:
    out = "C:\\Users\\bur_s\\AppData\\Local\\Temp\\opencode\\edge_ru.mp3"
    # ru-RU-Dmitry — мужской, ru-RU-Svetlana — женский
    for name, text, dest in (
        ("ru-RU-DmitryNeural", TEXT_RU, out),
        ("en-GB-RyanNeural", TEXT_EN, out.replace("ru", "en")),
    ):
        comm = edge_tts.Communicate(text, name)
        await comm.save(dest)
        print(f"[OK] {name} -> {dest}")


asyncio.run(main())