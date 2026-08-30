"""好友台账:以显示名为键的本地好友库(每账号独立 ledger.json)。

字段说明:
    name         聊天列表中的显示名(主键)
    nickname     抖音昵称(可能不同)
    short_id     抖音号(ShortId,不可变,扫描可得)
    user_id      抖音用户 id
    avatar       本地缓存头像 URL(/avatars/<id>/xxx)
    days         当前火花天数
    has_chat     是否存在会话(consumer 页出现即 True)
    selected     是否勾选为发送目标
    order        勾选顺序(置顶排序用)
    last_sent    最近一次发送时间
    last_msg     最近一次发送的文案(防重复)
    source       sync(同步) / scan(扫描) / manual(手动)
    confidence   high / low(昵称与显示名是否已对上)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from . import avatars
from .settings import account_dir
from .storage import read_json, write_json


def ledger_path(account_id: str) -> Path:
    return account_dir(account_id) / "ledger.json"


def _default_entry(name: str) -> dict:
    return {
        "name": name,
        "nickname": "",
        "account": "",       # 抖音号(如 doushi_123,同步时尽力识别)
        "short_id": "",
        "user_id": "",
        "avatar": "",        # 本地缓存路径 /avatars/<aid>/xxx(永不失效)
        "days": 0,
        "has_chat": False,
        "selected": False,
        "order": None,
        "last_sent": None,
        "last_msg": "",
        "source": "manual",
        "confidence": "low",
    }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_days(text: object) -> int:
    """从「🔥 12」「12 天」等文本提取天数;解析失败返回 0。"""
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else 0


def normalize_name(text: object) -> str:
    """去除不间断空格等不可见字符,仅用于匹配,不改原值。"""
    return str(text or "").replace("\u00a0", " ").strip()


def load(account_id: str, include_excluded: bool = False) -> list[dict]:
    """读取台账;默认过滤掉已被用户移除(excluded)的好友。"""
    data = read_json(ledger_path(account_id), [])
    entries = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                e = {**_default_entry(str(item["name"])), **item}
                if not include_excluded and e.get("excluded"):
                    continue
                entries.append(e)
    return entries


def _save(account_id: str, entries: list[dict]) -> None:
    """保存可见条目;被用户移除(excluded)的条目在文件中原样保留。

    所有调用方(load→改→save 的路径)都只操作可见条目,
    这里负责把文件里的 excluded 条目合并回来,避免同步/勾选时误删标记。
    """
    raw = read_json(ledger_path(account_id), [])
    if not isinstance(raw, list):
        raw = []
    kept = {normalize_name(e.get("name")) for e in entries}
    for old in raw:
        if isinstance(old, dict) and old.get("excluded") and normalize_name(old.get("name")) not in kept:
            entries.append(old)
    write_json(ledger_path(account_id), entries)


def _index(entries: list[dict]) -> dict[str, dict]:
    return {normalize_name(e.get("name")): e for e in entries}


def upsert_many(account_id: str, items: Iterable[dict]) -> dict:
    """批量合并同步/扫描结果:更新天数与会话存在性,保留勾选与发送历史。

    已被用户移除(excluded)的好友不会被重新加入。
    """
    all_entries = load(account_id, include_excluded=True)
    excluded = {normalize_name(e.get("name")) for e in all_entries if e.get("excluded")}
    entries = [e for e in all_entries if not e.get("excluded")]
    index = _index(entries)
    added = updated = 0
    for item in items:
        name = normalize_name(item.get("name"))
        if not name or name in excluded:
            continue
        # 头像本地化缓存:签名 URL 会过期,缓存到 /avatars/ 下长期可用
        avatar_url = str(item.get("avatar") or "")
        local_avatar = avatars.save(avatar_url, account_id) if avatar_url.startswith("http") else ""
        item = dict(item)
        item["avatar"] = local_avatar
        # 私信列表同步出来的好友必然存在会话;同步来源标记为 sync
        item["has_chat"] = True
        item["source"] = "sync"

        if name in index:
            entry = index[name]
            old_days = entry.get("days", 0)
            for k, v in item.items():
                if k in ("name", "selected", "order", "last_sent", "last_msg", "confidence", "source"):
                    continue
                # 头像下载失败时保留旧头像
                if k == "avatar" and not v:
                    continue
                entry[k] = v
            if entry.get("days", 0) != old_days or item.get("has_chat"):
                updated += 1
        else:
            entry = _default_entry(str(item.get("name")))
            for k, v in item.items():
                if k not in ("selected", "order", "last_sent", "last_msg"):
                    entry[k] = v
            entries.append(entry)
            index[name] = entry
            added += 1
    if added or updated:
        _save(account_id, entries)
    return {"added": added, "updated": updated, "total": len(entries)}


def selected(account_id: str) -> list[dict]:
    return [e for e in load(account_id) if e.get("selected")]


def set_selection(account_id: str, changes: Iterable[dict]) -> dict:
    """批量设置勾选:changes = [{name, selected, order?}]。未知名字自动新增(手动添加)。"""
    entries = load(account_id)
    index = _index(entries)
    updated = added = 0
    order_seq = 0
    for change in changes:
        name = normalize_name(change.get("name"))
        if not name:
            continue
        sel = bool(change.get("selected"))
        order = change.get("order")
        if sel:
            order_seq += 1
            order = order if order is not None else order_seq
        if name in index:
            entry = index[name]
            if bool(entry.get("selected")) != sel or entry.get("order") != (order if sel else None):
                entry["selected"] = sel
                entry["order"] = order if sel else None
                updated += 1
        else:
            entry = _default_entry(str(change.get("name")))
            entry["selected"] = sel
            entry["order"] = order if sel else None
            entry["source"] = "manual"
            entries.append(entry)
            index[name] = entry
            added += 1
    if updated or added:
        _save(account_id, entries)
    return {"updated": updated, "added": added}


def remove_names(account_id: str, names: Iterable[str]) -> dict:
    """移除好友:标记 excluded 并清除勾选,同步时不会再加入。仅影响本工具台账,
    不会解除抖音好友关系。"""
    data = read_json(ledger_path(account_id), [])
    if not isinstance(data, list):
        return {"removed": 0}
    wanted = {normalize_name(n) for n in names}
    removed = 0
    for entry in data:
        if isinstance(entry, dict) and normalize_name(entry.get("name")) in wanted:
            if not entry.get("excluded"):
                entry["excluded"] = True
                entry["selected"] = False
                entry["order"] = None
                removed += 1
            else:
                removed += 1  # 幂等
    if removed:
        _save_raw(account_id, data)
    return {"removed": removed}


def _save_raw(account_id: str, data: list[dict]) -> None:
    write_json(ledger_path(account_id), data)


def mark_sent(account_id: str, name: str, ok: bool, msg: str, via_scan: bool = False) -> None:
    """发送后回写:更新时间/文案;成功且非通道 B 时标记会话存在。"""
    entries = load(account_id)
    for entry in entries:
        if normalize_name(entry.get("name")) == normalize_name(name):
            entry["last_sent"] = _now()
            if ok:
                entry["last_msg"] = msg
                if not via_scan:
                    entry["has_chat"] = True
                    entry["confidence"] = "high" if entry.get("nickname") == entry.get("name") else entry.get("confidence")
            break
    _save(account_id, entries)


def stats(account_id: str) -> dict:
    """台账健康度报告。"""
    entries = load(account_id)
    now = datetime.now().astimezone()
    week_ago = (now - timedelta(days=7)).isoformat()
    top = sorted(entries, key=lambda e: -(e.get("days") or 0))[:10]
    return {
        "total": len(entries),
        "selected": sum(1 for e in entries if e.get("selected")),
        "high": sum(1 for e in entries if e.get("confidence") == "high"),
        "with_short_id": sum(1 for e in entries if e.get("short_id")),
        "top": [{"name": e["name"], "days": e.get("days", 0)} for e in top],
        "no_chat": [{"name": e["name"], "source": e.get("source", "")} for e in entries if not e.get("has_chat")],
        "recent7": [e["name"] for e in entries if str(e.get("last_sent") or "") >= week_ago],
    }
