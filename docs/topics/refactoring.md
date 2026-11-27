---
title: Рефакторинг
status: active
created: 2026-11-27
---

## Цель
Улучшить структуру и поддерживаемость кода TextToSpeech без изменения видимого пользователю поведения.

## Решено
- Агентские файлы игнорируются локально и глобально (`~/.config/git/ignore`); `docs/topics/` — исключение и хранится в git.
- `docs/*.py` — код проекта, под ignore не попадает.
- `edge` и `silero` — extras (`poetry install -E ...`), ruff — в группе `dev`, проверки обязательны после изменения кода.
- `torch` и `torchaudio` ограничены 2.11.x; Python — 3.14.x из-за ограничения `triton <3.15`.
- GUI переписан с Tkinter на PyQt6: `QMainWindow`, `QPlainTextEdit`, `QComboBox`, `QFileDialog`, `QMessageBox`; очередь событий из потока синтеза разбирается через `QTimer`.
- При открытии окно центрируется по доступной области экрана (`center_on_screen()` вызывается в `build_window()`).

## Сделано
- Проверки зависимостей и окружения: `pip check`, `poetry check --lock`, Poetry и IDE используют один `.venv`; версии приведены к lock.
- Исправлены команды установки extras, наведён порядок в `.idea`, добавлен ruff и исправлены его замечания.
- `src/texttospeech/app.py` переписан под Qt; сохранены поведение правок/сохранения, кодировок, выбора голоса и скорости, фонового синтеза и прогресса.
- Тесты переписаны под Qt с оффскрин-платформой (`tests/conftest.py`); `docs/screenshot.py` и `docs/screenshot_edit.py` теперь снимают `QWidget.grab()`.
- Убраны все упоминания Tkinter из кода и документации; README и `pyproject.toml` обновлены.
- Добавлено центрирование окна при запуске и тест на него.
- Проверки после изменений: `ruff check .` — All checks passed; `pytest -q` — 74 passed.

## Блокировка
Нет.

## Следующий шаг
Изменения зафиксированы коммитом; дальше закрыть тему или уточнить последующие задачи рефакторинга.

## Файлы
- `src/texttospeech/app.py`
- `src/texttospeech/engines/piper_engine.py`
- `src/texttospeech/voices.py`
- `main.py`
- `.gitignore`
- `pyproject.toml`
- `poetry.lock`
- `README.md`
- `docs/INDEX.md`
- `docs/decisions.md`
- `docs/*.py`
- `tests/conftest.py`
- `tests/test_app.py`
- `tests/test_synthesis.py`
- `.idea/workspace.xml`
- `.idea/inspectionProfiles/Project_Default.xml`

## Затронутые темы
- _заполняется при пересечении файлов с другими темами_

## Связи
- _заполняется, когда другая тема затронула файлы этой темы_
