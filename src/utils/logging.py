"""
JSONL logging for measurement records (Methods §Code and data availability).

Raw measurement logs (.jsonl format, one entry per 10-s window) are
archived on Zenodo (DOI: 10.5281/zenodo.XXXXXXX).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


class JSONLWriter:
    """Append-only JSONL log writer."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a", buffering=1)   # line-buffered

    def write(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record) + "\n")

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "JSONLWriter":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def load_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from a JSONL file."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
