"""好友头像本地缓存。

抖音网页版头像 URL 带签名,过期后无法访问。同步联系人时把头像下载到本地
data/avatars/<account_id>/<hash>.<ext>,网页端通过 /avatars/... 访问,长期有效。
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import requests

from .settings import AVATAR_ROOT

_TIMEOUT = 12
_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.Lock()
        return lock


def save(url: str, account_id: str) -> str:
    """下载头像到本地,返回可公开访问的相对路径;失败返回空串。"""
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return ""
    try:
        ext = Path(url.split("?")[0]).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        fname = f"{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}{ext}"
        d = AVATAR_ROOT / account_id
        fp = d / fname
        if fp.exists() and fp.stat().st_size > 0:
            return f"/avatars/{account_id}/{fname}"
        with _lock_for(f"{account_id}:{fname}"):
            if fp.exists() and fp.stat().st_size > 0:
                return f"/avatars/{account_id}/{fname}"
            d.mkdir(parents=True, exist_ok=True)
            resp = requests.get(url, timeout=_TIMEOUT, headers={"Referer": "https://www.douyin.com/"})
            resp.raise_for_status()
            tmp = fp.with_suffix(fp.suffix + ".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(fp)
        return f"/avatars/{account_id}/{fname}"
    except Exception:
        return ""
