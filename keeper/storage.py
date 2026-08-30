"""JSON 持久化:原子写入(临时文件 + rename),避免写一半损坏数据。"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def read_json(path: Path, default: Any = None) -> Any:
    """读取 JSON 文件;文件不存在或损坏时返回 default。"""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, data: Any) -> None:
    """原子写入 JSON(先写 .tmp 再 rename,防断电/崩溃产生半截文件)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(str(path)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(str(path)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
