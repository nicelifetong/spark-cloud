"""好友抖音号扫描(只读):打开创作者消息页,滚动好友列表并拦截 user_detail 接口响应。

背景:抖音网页版好友列表的 ShortId 需要带签名的接口才能拿到,裸 HTTP 无法复现,
因此采用「浏览器内滚动 + 响应拦截」的方式采集,全程不发送任何消息,属于纯只读操作。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from .browser import open_session
from .settings import account_dir

logger = logging.getLogger("spark")

CREATOR_URL = "https://creator.douyin.com/creator-micro/data/following/chat"
API_PATH = "aweme/v1/creator/im/user_detail/"

TAB_CANDIDATES = [
    'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]',
    'xpath=//*[contains(text(),"好友")]',
]

_SCROLL_JS = """
() => {
    const els = document.querySelectorAll('[class*="semi-list"], #sub-app ul');
    let el = null;
    for (const e of els) { if (e.scrollHeight > e.clientHeight + 10) { el = e; break; } }
    if (!el) {
        const all = [...document.querySelectorAll('div')].filter(
            x => x.scrollHeight > x.clientHeight + 100 && x.clientHeight > 100
        );
        if (all.length) el = all[0];
    }
    if (el && el.scrollTop + el.clientHeight < el.scrollHeight - 10) {
        el.scrollTop += 600;
        return true;
    }
    return false;
}
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _click_friends_tab(page) -> bool:
    for selector in TAB_CANDIDATES:
        try:
            loc = page.locator(selector)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


def _session_ok(page, context) -> str | None:
    if "passport" in page.url.lower() or "login" in page.url.lower():
        return f"创作者页跳转到登录页({page.url})"
    try:
        cookies = context.cookies()
        if not any(c.get("name", "").startswith("sessionid") for c in cookies):
            return "未检测到 sessionid cookie,登录态可能已过期"
    except Exception:
        return "无法读取 Cookie"
    return None


def _on_response(mapping: dict, urls: list[str]):
    def handler(resp):
        try:
            if API_PATH not in resp.url:
                return
            if len(urls) < 3:
                urls.append(resp.url)
            if resp.status != 200:
                return
            data = resp.json()
            for item in data.get("user_list", []) or []:
                user = item.get("user", {}) or {}
                sid = str(user.get("ShortId", "")).strip()
                nick = str(user.get("nickname", "")).strip()
                uid = str(item.get("user_id", ""))
                if sid:
                    mapping[sid] = {"nickname": nick, "user_id": uid}
        except Exception:
            pass
    return handler


def collect(account_id: str, max_scrolls: int | None = None, scroll_interval: float = 0.5) -> dict:
    """执行一次扫描,返回 {mapping, count, error}。"""
    result: dict = {"mapping": {}, "count": 0, "error": None}
    state = account_dir(account_id) / "state.json"
    if not state.exists():
        result["error"] = "该账号尚未上传登录态 state.json"
        return result
    if max_scrolls is None:
        from . import accounts as acc_store
        max_scrolls = acc_store.load_config(account_id).get("max_scrolls", 80)

    mapping: dict[str, dict] = {}
    urls: list[str] = []
    try:
        with open_session(storage_state=state) as (pw, browser, context, page):
            page.on("response", _on_response(mapping, urls))
            page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(10000)

            err = _session_ok(page, context)
            if err:
                result["error"] = err
                return result
            _click_friends_tab(page)
            page.wait_for_timeout(3000)

            stagnant = 0
            last_size = 0
            for _ in range(max_scrolls):
                try:
                    moved = bool(page.evaluate(_SCROLL_JS))
                except Exception:
                    moved = False
                time.sleep(scroll_interval)
                grew = len(mapping) > last_size
                last_size = len(mapping)
                if not moved and not grew:
                    stagnant += 1
                    if stagnant >= 6:
                        break
                else:
                    stagnant = 0

            result["mapping"] = mapping
            result["count"] = len(mapping)
            logger.info("[%s] 扫描完成:%s 条映射", account_id, len(mapping))
    except Exception as exc:
        logger.error("[%s] 扫描异常: %s", account_id, exc)
        result["error"] = f"扫描异常: {exc}"
    return result


def merge_into_ledger(account_id: str, mapping: dict) -> dict:
    """把扫描结果并入台账:昵称匹配的升级置信度;无记录的按昵称新建条目。"""
    from . import ledger as book
    entries = book.load(account_id)
    by_norm = {book.normalize_name(e.get("name")): e for e in entries}
    joined = added = updated = 0
    for sid, info in (mapping or {}).items():
        nick = str(info.get("nickname", "")).strip()
        uid = str(info.get("user_id", ""))
        target = by_norm.get(book.normalize_name(nick))
        if target is not None:
            changed = False
            for key, value in (("short_id", sid), ("nickname", nick), ("user_id", uid)):
                if target.get(key) != value:
                    target[key] = value
                    changed = True
            if not target.get("source") or target.get("source") != "scan":
                target["source"] = "scan"
                changed = True
            if target.get("confidence") != "high" and nick == target.get("name"):
                target["confidence"] = "high"
                changed = True
            joined += 1
            updated += 1 if changed else 0
        else:
            from .ledger import _default_entry
            entry = _default_entry(nick or sid)
            entry.update({"nickname": nick, "short_id": sid, "user_id": uid, "source": "scan"})
            entries.append(entry)
            by_norm[book.normalize_name(nick)] = entry
            added += 1
    if added or updated:
        book._save(account_id, entries)
    return {"joined": joined, "added": added, "updated": updated, "total": len(entries)}
