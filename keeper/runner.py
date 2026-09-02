"""业务流水线:同步联系人 / 发送续火花 / 好友扫描 / 强制停止。

并发控制:
- 每个账号一把运行锁,同一账号不允许并发执行;
- stop 通过事件标志请求,工作线程在好友循环中检查并提前退出。
"""
from __future__ import annotations

import logging
import random
import threading
from datetime import datetime

from . import accounts as acc_store
from . import history, ledger as book, notify
from . import messages, runtime as rt, scan, stickers
from . import douyin
from .settings import DEFAULT_ACCOUNT

logger = logging.getLogger("spark")

_account_locks: dict[str, threading.Lock] = {}
_stop_flags: dict[str, threading.Event] = {}
_busy: set[str] = set()
_guard = threading.Lock()


def _lock_for(account_id: str) -> threading.Lock:
    with _guard:
        lock = _account_locks.get(account_id)
        if lock is None:
            lock = _account_locks[account_id] = threading.Lock()
        return lock


def _flag_for(account_id: str) -> threading.Event:
    with _guard:
        flag = _stop_flags.get(account_id)
        if flag is None:
            flag = _stop_flags[account_id] = threading.Event()
        return flag


def is_busy(account_id: str) -> bool:
    return account_id in _busy


def request_stop(account_id: str) -> None:
    _flag_for(account_id).set()


def request_stop_all() -> None:
    for aid in list(_stop_flags):
        _stop_flags[aid].set()
    for aid in list(_busy):
        _flag_for(aid).set()


def reset_all() -> None:
    """强制重置:清空忙碌标记并释放锁(顶栏「停止」按钮)。"""
    with _guard:
        for aid in list(_busy):
            _busy.discard(aid)
    for aid in list(_stop_flags):
        _stop_flags[aid].clear()
    for aid in list(_account_locks):
        lock = _account_locks[aid]
        try:
            if lock.locked():
                lock.release()
        except Exception:
            pass
    logger.info("已强制重置全部运行状态")


def reset(account_id: str) -> None:
    """强制重置单个账号的运行状态。"""
    _flag_for(account_id).clear()
    with _guard:
        _busy.discard(account_id)
    lock = _lock_for(account_id)
    try:
        if lock.locked():
            lock.release()
    except Exception:
        pass
    logger.info("[%s] 已强制重置运行状态", account_id)


# ---------------- 同步联系人 ----------------

def _sync_via_node(account_id: str) -> dict:
    """Termux 本地回退:用 Node + playwright-core + 系统 chromium 同步联系人。

    手机装不了 Python playwright,但能装 nodejs + chromium(x11-repo),
    scripts/sync_friends.js 用它们复刻 sync_friends_page 的抓取逻辑。
    """
    import json
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    script = Path(__file__).resolve().parents[1] / "scripts" / "sync_friends.js"
    if not node or not script.exists():
        return {"names": [], "error": (
            "此环境无 playwright 且 Node 本地同步不可用;安装:"
            "pkg install nodejs-lts x11-repo -y && pkg install chromium -y"
            " && npm install playwright-core(见 README 路线 E)")}
    state = account_dir(account_id) / "state.json"
    if not state.exists():
        return {"names": [], "error": "该账号尚未上传登录态 state.json"}
    try:
        proc = subprocess.run(
            [node, str(script), "--state", str(state), "--max-rounds", "20"],
            capture_output=True, text=True, timeout=420,
        )
        data = {}
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith("RESULT:"):
                data = json.loads(line[len("RESULT:"):])
                break
        names = data.get("names") or []
        if not names and not data.get("error"):
            tail = (proc.stderr or "").strip().splitlines()
            data = {"names": [], "error": tail[-1] if tail else "Node 本地同步失败"}
        return {"names": names, "error": data.get("error")}
    except subprocess.TimeoutExpired:
        return {"names": [], "error": "Node 本地同步超时(7 分钟)"}
    except Exception as exc:  # noqa: BLE001
        return {"names": [], "error": f"Node 本地同步异常: {exc}"}


def sync_contacts(account_id: str) -> dict:
    """后台线程:打开私信页拉取联系人 → 合并进台账。"""
    if not _lock_for(account_id).acquire(blocking=False):
        return {"ok": False, "reason": "该账号已有任务在运行"}
    with _guard:
        _busy.add(account_id)
    try:
        rt.set_running(account_id, True)
        try:
            from .browser import HAS_PLAYWRIGHT
            if HAS_PLAYWRIGHT:
                data = douyin.sync_friends_page(account_id)
            else:
                data = _sync_via_node(account_id)
            error = data.get("error")
            if error:
                rt.record_sync(account_id, 0, error)
                logger.warning("[%s] 同步联系人失败: %s", account_id, error)
                return {"ok": False, "reason": error}
            stats = book.upsert_many(account_id, data["names"])
            rt.record_sync(account_id, len(data["names"]), None)
            logger.info("[%s] 同步完成:新增 %s,更新 %s,共 %s", account_id, stats["added"], stats["updated"], stats["total"])
            return {"ok": True, **stats}
        finally:
            rt.set_running(account_id, False)
    finally:
        with _guard:
            _busy.discard(account_id)
        _lock_for(account_id).release()


# ---------------- 发送续火花 ----------------

def pending_targets(account_id: str, only_names: list[str] | None = None) -> list[dict]:
    """计算本次运行真正要发的人:勾选集合 + 通道判定(会话 or 允许首条)。"""
    cfg = acc_store.load_config(account_id)
    entries = book.selected(account_id)
    if only_names is not None:
        wanted = set(only_names)
        entries = [e for e in entries if e.get("name") in wanted]
    limit = int(cfg.get("max_per_run", 0) or 0)
    if limit > 0:
        entries = entries[:limit]
    out: list[dict] = []
    b = rt.load(account_id)["b_channel"]
    today = datetime.now().astimezone().date().isoformat()
    first_left = int(cfg.get("first_limit", 1) or 1)
    if b.get("date") == today:
        first_left = max(0, first_left - int(b.get("count", 0)))
    allow_first = bool(cfg.get("allow_first"))
    for e in entries:
        if e.get("has_chat"):
            out.append({**e, "channel": "consumer"})
        elif allow_first and first_left > 0:
            out.append({**e, "channel": "creator"})
    return out


def run_once(account_id: str, dry: bool = False, only_names: list[str] | None = None, headed: bool = False,
             auto: bool = False) -> dict:
    """执行一次发送(auto=True 表示自动调度触发,当日已发则跳过;手动触发放行)。"""
    if not _lock_for(account_id).acquire(blocking=False):
        return {"ok": False, "reason": "该账号已有任务在运行"}
    with _guard:
        _busy.add(account_id)
    flag = _flag_for(account_id)
    flag.clear()
    try:
        rt.set_running(account_id, True)
        try:
            cfg = acc_store.load_config(account_id)
            # 自动调度当日门禁:台账里任一好友 last_sent 是今天 → 整轮跳过(手动触发放行)
            if auto and not dry and not only_names:
                from . import ledger as _ledger
                from datetime import datetime as _dt
                _today = _dt.now().astimezone().strftime("%Y-%m-%d")
                if any(str(e.get("last_sent") or "").startswith(_today) for e in _ledger.load(account_id)):
                    logger.info("[%s] 今日已发送,自动调度跳过", account_id)
                    result = {"at": _now(), "dry_run": False, "ok": [], "failed": [], "skipped": [],
                              "note": "今日已发送,自动调度跳过"}
                    rt.record_run(account_id, result)
                    return {"started": True, **result}
            targets = pending_targets(account_id, only_names)
            if not targets:
                logger.info("[%s] 没有待发送目标,跳过", account_id)
                result = {"at": _now(), "dry_run": bool(dry), "ok": [], "failed": [], "skipped": [], "note": "无目标"}
                rt.record_run(account_id, result)
                return {"started": True, **result}

            # 好友差异:skip 的好友本轮直接跳过
            overrides = cfg.get("friend_overrides") or {}
            skipped_names = [t["name"] for t in targets if (overrides.get(t["name"]) or {}).get("skip")]
            if skipped_names:
                targets = [t for t in targets if t["name"] not in skipped_names]
                logger.info("[%s] 按差异设置跳过 %s 人: %s", account_id, len(skipped_names), "、".join(skipped_names))
            if not targets:
                result = {"at": _now(), "dry_run": bool(dry), "ok": [], "failed": [],
                          "skipped": skipped_names, "note": "全部好友被差异设置跳过"}
                rt.record_run(account_id, result)
                return {"started": True, **result}

            base_pool = messages.build_pool(cfg)
            sticker_on = bool(cfg.get("sticker_enabled")) and not dry
            base_chance = int(cfg.get("sticker_chance", 30) or 0)
            for entry in targets:
                ov = overrides.get(entry["name"]) or {}
                opool = [str(m) for m in (ov.get("pool") or []) if str(m).strip()] or base_pool
                entry["text"] = messages.pick(opool, str(entry.get("last_msg", "")))
                try:
                    ch = base_chance if ov.get("sticker_chance") in (None, "") else int(ov["sticker_chance"])
                except (TypeError, ValueError):
                    ch = base_chance
                entry["sticker"] = (
                    stickers.pick_random(account_id)
                    if sticker_on and ch > 0 and random.random() * 100 < ch
                    else None
                )

            gap = (int(cfg.get("gap_min", 6)), int(cfg.get("gap_max", 12)))
            result = douyin.run_send_page(
                account_id, targets, dry_run=dry, headless=not headed, gap=gap,
            )
            result["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            result["dry_run"] = bool(dry)

            # 回写台账
            for name in result.get("ok", []):
                entry = next((t for t in targets if t["name"] == name), None)
                book.mark_sent(account_id, name, True, entry["text"] if entry else "", via_scan=bool(entry and entry.get("channel") == "creator"))
                if entry and entry.get("channel") == "creator" and not dry:
                    rt.bump_b_channel(account_id)
            for item in result.get("failed", []):
                if item.get("name") and item["name"] != "_system":
                    book.mark_sent(account_id, item["name"], False, "")

            # 发送历史(功能1)
            for name in result.get("ok", []):
                entry = next((t for t in targets if t["name"] == name), None)
                history.record(account_id, name, entry["text"] if entry else "",
                               entry.get("sticker") if entry else None, True, dry=dry)
            for item in result.get("failed", []):
                nm = item.get("name", "")
                if nm and nm != "_system":
                    history.record(account_id, nm, "", None, False,
                                   item.get("reason", ""), dry=dry)
            # 事件通知(功能2)
            if not dry:
                _notify_result(account_id, result)

            rt.record_run(account_id, result)
            logger.info("[%s] 发送完成:成功 %s,失败 %s, dry=%s", account_id, len(result["ok"]), len(result["failed"]), dry)
            return {"started": True, **result}
        finally:
            rt.set_running(account_id, False)
    finally:
        with _guard:
            _busy.discard(account_id)
        _lock_for(account_id).release()


def _notify_result(account_id: str, result: dict) -> None:
    """发送结束后按事件推通知(内部吞掉一切异常)。"""
    try:
        if result.get("logged_out"):
            notify.send(f"续火花:账号「{account_id}」登录态失效",
                        "抖音登录已过期,请打开网页 → 凭证页重新扫码登录。",
                        event="login_expired")
        if result.get("rate_limited"):
            notify.send(f"续火花:账号「{account_id}」触发限流",
                        "本轮发送已自动停止,建议调大间隔或减少单轮人数。",
                        event="rate_limited")
        failed = [f for f in result.get("failed", []) if f.get("name") != "_system"]
        if failed:
            lines = "\n".join(f"· {f.get('name')}: {f.get('reason', '')}" for f in failed[:10])
            notify.send(f"续火花:账号「{account_id}」{len(failed)} 人发送失败", lines,
                        event="send_fail")
        sent = result.get("ok") or []
        if sent:
            names = "、".join(str(n) for n in sent[:8])
            extra = f" 等 {len(sent)} 人" if len(sent) > 8 else ""
            notify.send(f"续火花:账号「{account_id}」本轮成功 {len(sent)} 人",
                        f"已发送:{names}{extra}", event="send_ok")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] 通知推送异常: %s", account_id, exc)


# ---------------- 好友扫描(只读) ----------------

def run_scan(account_id: str) -> dict:
    if not _lock_for(account_id).acquire(blocking=False):
        return {"ok": False, "reason": "该账号已有任务在运行"}
    with _guard:
        _busy.add(account_id)
    try:
        rt.set_running(account_id, True)
        try:
            data = scan.collect(account_id)
            if data.get("error"):
                rt.save(account_id, harvest_last={"at": data.get("at", _now()), "error": data["error"]})
                return {"ok": False, "reason": data["error"]}
            merged = scan.merge_into_ledger(account_id, data["mapping"])
            summary = {"at": _now(), "count": data["count"], **merged}
            rt.save(account_id, harvest_last=summary)
            logger.info("[%s] 扫描并合并完成:count=%s", account_id, data["count"])
            return {"ok": True, **summary}
        finally:
            rt.set_running(account_id, False)
    finally:
        with _guard:
            _busy.discard(account_id)
        _lock_for(account_id).release()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
