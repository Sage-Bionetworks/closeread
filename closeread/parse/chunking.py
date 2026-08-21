"""Window splitting. Windows cover the whole document; offsets locate in the
parent text (spec §9.6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    index: int
    start: int
    end: int

    def slice(self, text: str) -> str:
        return text[self.start : self.end]


def make_windows(text_length: int, window_chars: int = 30_000, overlap: int = 1_500) -> list[Window]:
    if window_chars <= 0:
        raise ValueError("window_chars must be positive")
    if overlap < 0 or overlap >= window_chars:
        raise ValueError("overlap must be in [0, window_chars)")
    if text_length <= 0:
        return []
    if text_length <= window_chars:
        return [Window(0, 0, text_length)]
    step = window_chars - overlap
    windows: list[Window] = []
    start = 0
    i = 0
    while start < text_length:
        end = min(start + window_chars, text_length)
        windows.append(Window(i, start, end))
        if end == text_length:
            break
        start += step
        i += 1
    return windows
