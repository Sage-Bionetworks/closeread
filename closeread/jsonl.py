"""JSONL read/write helpers. JSONL is canonical (spec §8.1)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_jsonl(path: Path, rows: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w") as fh:
        for row in rows:
            if isinstance(row, BaseModel):
                fh.write(row.model_dump_json())
            else:
                fh.write(json.dumps(row, ensure_ascii=False, default=str))
            fh.write("\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
