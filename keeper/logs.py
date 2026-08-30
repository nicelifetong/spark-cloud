"""日志:控制台 + 文件 + 内存环形缓冲。

环形缓冲供 Web 端 /api/.../logs 实时读取;文件日志落盘 data/logs/app.log
以及每个账号独立 data/accounts/<id>/logs/runtime.log。
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path

from .settings import DATA

RING_SIZE = 600
_ring: deque[str] = deque(maxlen=RING_SIZE)
_guard = threading.Lock()
_initialized = False
_file_handlers: dict[str, logging.FileHandler] = {}


def _default_formatter() -> logging.Formatter:
    return logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            with _guard:
                _ring.append(self.format(record))
        except Exception:
            pass


def setup() -> logging.Logger:
    """初始化全局 logger(spark)。幂等:多次调用只配置一次。"""
    global _initialized
    logger = logging.getLogger("spark")
    if _initialized:
        return logger
    logger.setLevel(logging.INFO)

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "logs").mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(DATA / "logs" / "app.log", encoding="utf-8")
    fh.setFormatter(_default_formatter())
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(_default_formatter())
    logger.addHandler(sh)

    rh = RingHandler()
    rh.setFormatter(_default_formatter())
    logger.addHandler(rh)

    _initialized = True
    return logger


def attach_account_file(account_id: str) -> None:
    """为账号追加独立日志文件句柄。"""
    logger = logging.getLogger("spark")
    if account_id in _file_handlers:
        return
    try:
        p = DATA / "accounts" / account_id / "logs"
        p.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(p / "runtime.log", encoding="utf-8")
        fh.setFormatter(_default_formatter())
        logger.addHandler(fh)
        _file_handlers[account_id] = fh
    except Exception:
        pass


def recent(n: int = 300) -> list[str]:
    """最近 n 条日志(供 Web 端展示)。"""
    with _guard:
        return list(_ring)[-n:]
