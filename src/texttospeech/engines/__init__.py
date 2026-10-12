"""Движки синтеза речи."""

from .base import Engine, EngineUnavailable, SynthesisResult
from .piper_engine import PiperEngine, split_text

__all__ = [
    "Engine",
    "EngineUnavailable",
    "PiperEngine",
    "SynthesisResult",
    "split_text",
]