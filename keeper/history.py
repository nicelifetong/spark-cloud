"""发送历史:data/accounts/<id>/history.jsonl(每行一条 JSON)。

- record():发送完成(成功/失败)后追加一条;
- recent():倒序读最近 N 条;
- stats():月度/累计统计 + 每好友最近成功时间。
文件超过 2000 条时裁剪到最近 1500 条,防止无限增长。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from .settings import account_dir

logger = logging.getLogger("spark")

_MAX_LINES = 2000
_KEEP_LINES = 1500


def _path(account_id: str):
    return account_dir(account_id) / "history.jsonl"


def record(account_id: str, name: str, text: str, sticker: str | None,
           ok: bool, reason: str = "", dry: bool = False) -> None:
    """追加一条发送记录(异常不抛出,不影响发送流程)。"""
    entry = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "name": str(name),
        "text": str(text or ""),
        "sticker": bool(sticker),
        "ok": bool(ok),
        "reason": str(reason or "")[:200],
        "dry": bool(dry),
    }
    try:
        _path(account_id).parent.mkdir(parents=True, exist_ok=True)
        with open(_path(account_id), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _maybe_trim(account_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] 写发送历史失败: %s", account_id, exc)


def _read_all(account_id: str) -> list[dict]:
    try:
        with open(_path(account_id), encoding="utf-8") as fh:
            out = []
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return out
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] 读发送历史失败: %s", account_id, exc)
        return []


def _maybe_trim(account_id: str) -> None:
    lines = _read_all(account_id)
    if len(lines) <= _MAX_LINES:
        return
    keep = lines[-_KEEP_LINES:]
    with open(_path(account_id), "w", encoding="utf-8") as fh:
        for item in keep:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def recent(account_id: str, limit: int = 100) -> list[dict]:
    """最近 limit 条(新的在前)。"""
    limit = max(1, min(1000, int(limit or 100)))
    return list(reversed(_read_all(account_id)))[:limit]


def stats(account_id: str) -> dict:
    """统计看板:本月/累计成功失败、成功率、每好友最近一次成功。"""
    now = datetime.now().astimezone()
    month_prefix = now.strftime("%Y-%m")
    records = _read_all(account_id)
    real = [r for r in records if not r.get("dry")]

    def _count(rs: list[dict]) -> tuple[int, int]:
        ok = sum(1 for r in rs if r.get("ok"))
        return ok, len(rs) - ok

    m_ok, m_fail = _count([r for r in real if str(r.get("ts", "")).startswith(month_prefix)])
    t_ok, t_fail = _count(real)
    total = m_ok + m_fail

    per_friend: dict[str, dict] = {}
    for r in real:
        name = str(r.get("name") or "")
        if not name or name == "_system":
            continue
        slot = per_friend.setdefault(name, {"name": name, "last_ok": None, "ok": 0, "fail": 0})
        if r.get("ok"):
            slot["ok"] += 1
            if not slot["last_ok"] or str(r.get("ts", "")) > slot["last_ok"]:
                slot["last_ok"] = r.get("ts")
        else:
            slot["fail"] += 1

    return {
        "month_ok": m_ok,
        "month_fail": m_fail,
        "total_ok": t_ok,
        "total_fail": t_fail,
        "month_rate": round(m_ok * 100 / total) if total else None,
        "friends": sorted(per_friend.values(), key=lambda x: x.get("last_ok") or "", reverse=True),
    }
