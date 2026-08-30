"""多账号注册表与每账号配置。

设计:
- 所有账号(含默认 default)统一存放在 data/accounts/<id>/,结构一致;
- 账号注册表 data/accounts.json 只存元信息;业务数据各账号目录独立;
- 删除账号时把整个目录移动到 data/archived/<id>_<时间戳> 归档,可随时恢复;
- 全局浏览器并发名额用信号量控制(见 browser.py),防止多账号同时开太多浏览器触发风控。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path

from .messages import THEMES as DEFAULT_THEMES
from .settings import ACCOUNTS_ROOT, DEFAULT_ACCOUNT, DEFAULT_CONFIG, DATA, account_dir
from .storage import read_json, write_json

REGISTRY_PATH = DATA / "accounts.json"
_lock = threading.Lock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- 账号元信息 ----------

def _fresh_meta(account_id: str, name: str, note: str = "") -> dict:
    return {
        "id": account_id,
        "name": name,
        "note": note,
        "enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _load_registry() -> dict[str, dict]:
    data = read_json(REGISTRY_PATH, [])
    out: dict[str, dict] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
    return out


def _save_registry(reg: dict[str, dict]) -> None:
    entries = sorted(reg.values(), key=lambda a: a.get("created_at", ""))
    write_json(REGISTRY_PATH, entries)


def list_accounts() -> list[dict]:
    """全部账号列表(默认账号始终存在),附带目录与登录态信息。"""
    reg = _load_registry()
    ids = [DEFAULT_ACCOUNT] + sorted(k for k in reg if k != DEFAULT_ACCOUNT)
    out = []
    for aid in ids:
        meta = reg.get(aid) or _fresh_meta(aid, "默认账号")
        d = account_dir(aid)
        out.append({
            **meta,
            "is_default": aid == DEFAULT_ACCOUNT,
            "dir": str(d),
            "state_file_exists": (d / "state.json").exists(),
        })
    return out


def get_account(account_id: str) -> dict | None:
    if account_id == DEFAULT_ACCOUNT:
        return {**_fresh_meta(DEFAULT_ACCOUNT, "默认账号"), "is_default": True, "dir": str(account_dir(DEFAULT_ACCOUNT))}
    reg = _load_registry()
    meta = reg.get(account_id)
    if not meta:
        return None
    return {**meta, "is_default": False, "dir": str(account_dir(account_id))}


def exists(account_id: str) -> bool:
    return account_id == DEFAULT_ACCOUNT or account_id in _load_registry()


def create(name: str = "", note: str = "") -> dict:
    """新建账号:唯一 id + 独立数据目录。"""
    with _lock:
        reg = _load_registry()
        while True:
            aid = "acc_" + uuid.uuid4().hex[:8]
            if aid not in reg:
                break
        meta = _fresh_meta(aid, (name or "").strip() or f"账号 {aid[-4:]}", (note or "").strip())
        reg[aid] = meta
        _save_registry(reg)
    d = account_dir(aid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return {**meta, "is_default": False, "dir": str(d)}


def update(account_id: str, name: str | None = None, note: str | None = None, enabled: bool | None = None) -> dict | None:
    """更新账号(改名/备注/启停)。默认账号不允许停用。"""
    if account_id == DEFAULT_ACCOUNT:
        return None
    with _lock:
        reg = _load_registry()
        meta = reg.get(account_id)
        if not meta:
            return None
        if name is not None:
            meta["name"] = (name or "").strip() or meta["name"]
        if note is not None:
            meta["note"] = (note or "").strip()
        if enabled is not None:
            meta["enabled"] = bool(enabled)
        meta["updated_at"] = _now()
        _save_registry(reg)
    return get_account(account_id)


def remove(account_id: str) -> bool:
    """删除账号:注册表移除 + 目录归档到 data/archived/。"""
    if account_id == DEFAULT_ACCOUNT:
        return False
    with _lock:
        reg = _load_registry()
        if account_id not in reg:
            return False
        del reg[account_id]
        _save_registry(reg)
    d = account_dir(account_id)
    if d.exists():
        try:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dst = DATA / "archived" / f"{account_id}_{stamp}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            d.rename(dst)
        except Exception:
            pass
    return True


# ---------- 每账号配置 ----------

def config_path(account_id: str) -> Path:
    return account_dir(account_id) / "config.json"


def load_config(account_id: str) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    data = read_json(config_path(account_id), {})
    if isinstance(data, dict):
        for k, v in data.items():
            if k in DEFAULT_CONFIG:
                cfg[k] = v
    return cfg


def save_config(account_id: str, patch: dict | None = None) -> dict:
    """合并保存配置并做基本校验,返回规范化后的完整配置。"""
    merged = load_config(account_id)
    if patch:
        for k, v in patch.items():
            if k in DEFAULT_CONFIG:
                merged[k] = v

    # 校验时间格式 HH:MM
    raw_time = str(merged.get("schedule_time", "21:00"))
    try:
        hh, mm = raw_time.split(":")
        merged["schedule_time"] = f"{int(hh):02d}:{int(mm):02d}"
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError("时间无效")
    except Exception:
        raise ValueError("schedule_time 必须是 HH:MM 格式")

    for key in ("jitter_minutes", "gap_min", "gap_max", "max_per_run", "first_limit", "max_scrolls"):
        try:
            merged[key] = max(0, int(merged.get(key, DEFAULT_CONFIG[key])))
        except (TypeError, ValueError):
            raise ValueError(f"{key} 必须是整数")
    if merged["gap_max"] < merged["gap_min"]:
        merged["gap_max"] = merged["gap_min"]

    merged["messages"] = [str(m) for m in merged.get("messages", []) if str(m).strip()]
    if not merged["messages"] and not [t for t in (merged.get("themes") or []) if t in DEFAULT_THEMES]:
        merged["messages"] = ["🔥 续火花"]

    merged["themes"] = [str(t) for t in (merged.get("themes") or []) if t in DEFAULT_THEMES]
    merged["sticker_enabled"] = bool(merged.get("sticker_enabled"))
    try:
        merged["sticker_chance"] = min(100, max(0, int(merged.get("sticker_chance", 30))))
    except (TypeError, ValueError):
        merged["sticker_chance"] = 30

    merged["auto_enabled"] = bool(merged.get("auto_enabled"))
    merged["allow_first"] = bool(merged.get("allow_first"))

    # 好友差异规范化(功能5)
    norm_ov: dict = {}
    raw_ov = merged.get("friend_overrides")
    if isinstance(raw_ov, dict):
        for fname, rule in raw_ov.items():
            fname = str(fname).strip()
            if not fname or not isinstance(rule, dict):
                continue
            item = {"skip": bool(rule.get("skip")),
                    "pool": [str(m) for m in (rule.get("pool") or []) if str(m).strip()][:50],
                    "sticker_chance": None}
            try:
                sc = rule.get("sticker_chance")
                item["sticker_chance"] = None if sc in (None, "") else min(100, max(0, int(sc)))
            except (TypeError, ValueError):
                item["sticker_chance"] = None
            norm_ov[fname] = item
    merged["friend_overrides"] = norm_ov

    day = str(merged.get("harvest_day") or "off").strip().lower()
    merged["harvest_day"] = day if day in {"mon", "tue", "wed", "thu", "fri", "sat", "sun", "off"} else "off"

    write_json(config_path(account_id), merged)
    return merged


def ensure_account_dir(account_id: str) -> Path:
    d = account_dir(account_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "logs").mkdir(parents=True, exist_ok=True)
    return d
