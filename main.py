"""Точка входа для запуска без установки пакета.

    poetry run python main.py

Обычно удобнее запускать как установленную команду:

    poetry run texttospeech
"""
from texttospeech.app import main

if __name__ == "__main__":
    main()