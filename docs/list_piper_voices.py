"""Список одноголосых medium-моделей Piper для русского и английского."""
import json
import urllib.request

URL = "https://huggingface.co/rhasspy/piper-voices/raw/main/voices.json"

with urllib.request.urlopen(URL, timeout=60) as r:
    catalog = json.load(r)

for prefix in ("ru_RU", "en_US", "en_GB"):
    rows = []
    for key, entry in catalog.items():
        if not key.startswith(prefix):
            continue
        if "medium" not in key:
            continue
        if "high" in key or "low" in key or "x_low" in key:
            continue
        if key.startswith("en_US-libritts") or key.startswith("en_US-mike") \
                or key.startswith("en_US-ljspeech") or key.startswith("en_US-norman") \
                or key.startswith("en_US-reza"):
            continue
        lang = entry.get("language", {})
        speakers = entry.get("speaker_id_map", {})
        if speakers:
            continue  # многоголосые пропускаем
        rows.append((key, lang.get("name_native", ""), lang.get("name_english", "")))

    print(f"=== {prefix}: {len(rows)} ===")
    for key, native, english in sorted(rows):
        print(f"  {key:32s} {native:12s} {english}")