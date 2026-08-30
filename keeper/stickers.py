"""每账号表情包库:存储于 data/accounts/<id>/stickers/,发送时随机抽取。

- 仅允许图片扩展(jpg/png/webp/gif);
- 文件名统一改为 <时间戳>_<随机>.<ext>,避免路径注入与重名覆盖;
- 删除/读取都限制在本账号目录内。
"""
from __future__ import annotations

import random
import time
import uuid
from pathlib import Path

from .settings import account_dir

STICKER_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}


def stickers_dir(account_id: str) -> Path:
    return account_dir(account_id) / "stickers"


def list_stickers(account_id: str) -> list[str]:
    """按上传时间(文件名时间戳)返回全部表情包文件名。"""
    d = stickers_dir(account_id)
    if not d.is_dir():
        return []
    out = [f.name for f in d.iterdir() if f.is_file() and f.suffix.lower().lstrip(".") in STICKER_EXTS]
    return sorted(out)


def save_sticker(account_id: str, filename: str, raw: bytes) -> str:
    """保存一张表情包,返回落盘文件名。调用方负责扩展名/大小/魔数校验。"""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "png").lower()
    if ext == "jpeg":
        ext = "jpg"
    d = stickers_dir(account_id)
    d.mkdir(parents=True, exist_ok=True)
    name = f"{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}.{ext}"
    (d / name).write_bytes(raw)
    return name


def delete_sticker(account_id: str, name: str) -> bool:
    """删除指定表情包;路径逃逸或不存在返回 False。"""
    d = stickers_dir(account_id).resolve()
    target = (d / name).resolve()
    if not str(target).startswith(str(d)) or target.parent != d:
        return False
    if target.is_file():
        target.unlink(missing_ok=True)
        return True
    return False


def pick_random(account_id: str) -> Path | None:
    """随机抽一张表情包;库为空返回 None。"""
    names = list_stickers(account_id)
    if not names:
        return None
    return stickers_dir(account_id) / random.choice(names)
