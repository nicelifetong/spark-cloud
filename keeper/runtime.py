"""每账号运行状态持久化(runtime.json):会话状态、上次运行、同步时间、B 通道计数。"""
from __future__ import annotations

from .settings import account_dir
from .storage import read_json, write_json


def _path(account_id: str):
    return account_dir(account_id) / "runtime.json"


def _default() -> dict:
    return {
        "session_status": "unknown",
        "running": False,
        "last_run": None,
        "contacts_at": None,
        "contacts_error": None,
        "harvest_last": None,
        "b_channel": {"date": None, "count": 0},
    }


def load(account_id: str) -> dict:
    rt = _default()
    data = read_json(_path(account_id), {})
    if isinstance(data, dict):
        rt.update({k: v for k, v in data.items() if k in rt})
    return rt


def save(account_id: str, **fields) -> None:
    rt = load(account_id)
    rt.update(fields)
    write_json(_path(account_id), rt)


def set_running(account_id: str, value: bool) -> None:
    save(account_id, running=bool(value))


def record_run(account_id: str, result: dict) -> None:
    """运行结束回写:记录 last_run 与会话状态推断。"""
    if result.get("logged_out"):
        session = "expired"
    elif result.get("ok") and not result.get("failed"):
        session = "ok"
    elif result.get("ok"):
        session = "partial"
    elif result.get("failed"):
        session = "failed"
    else:
        session = "ok"
    save(account_id, last_run=result, session_status=session, running=False)


def record_sync(account_id: str, count: int, error: str | None) -> None:
    save(account_id, contacts_at=None if error else _now(), contacts_error=error)


def _now() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")


def bump_b_channel(account_id: str) -> None:
    """B 通道(首条消息)今日计数 +1;跨天自动归零。"""
    rt = load(account_id)
    today = _now()[:10]
    if rt["b_channel"].get("date") != today:
        rt["b_channel"] = {"date": today, "count": 1}
    else:
        rt["b_channel"]["count"] = rt["b_channel"].get("count", 0) + 1
    write_json(_path(account_id), rt)
