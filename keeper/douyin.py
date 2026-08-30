"""抖音私信页自动化。

通过 Playwright 操作抖音网页版私信页面:
- 打开会话页并校验登录态;
- 滚动同步聊天列表(好友名 + 火花天数 + 头像);
- 定位好友并发送消息(带防误发校验);
- 检测限流/验证浮层,命中立即停手。

实现说明:选择器面向抖音现行网页结构,若页面改版导致失效,优先看日志中的
「定位失败」类提示并到 .github/ISSUE_TEMPLATE 反馈,勿盲目重试刷接口。
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from pathlib import Path

from .browser import open_session
from .settings import account_dir

logger = logging.getLogger("spark")

CHAT_URL = "https://www.douyin.com/chat"

LOGIN_MARKERS = ["扫码登录", "验证码登录", "登录后查看", "登录后即可"]

RATE_LIMIT_KEYWORDS = [
    "操作频繁", "操作太频繁", "发送过于频繁", "请稍后再试", "安全验证",
    "滑动验证", "验证码", "验证中心", "人机验证", "网络异常", "请勿频繁",
]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save_error_shot(page, account_id: str) -> None:
    """出错时保存整页截图,便于排查。"""
    try:
        shot = account_dir(account_id) / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=str(shot), timeout=5000)
        logger.info("已保存错误截图: %s", shot)
    except Exception:
        pass


# ---------------- 登录态检测 ----------------

def check_login(page) -> tuple[bool, str]:
    """返回 (是否已登录, 说明)。宁可误报,不硬跑过期登录态。"""
    url = page.url
    if "login" in url.lower() or "passport" in url.lower():
        return False, f"页面跳转到登录页({url})"
    try:
        qr = page.locator("#animate_qrcode_container")
        if qr.count() and qr.first.is_visible():
            return False, "页面出现扫码登录二维码,登录态已过期"
    except Exception:
        pass
    for text in LOGIN_MARKERS:
        try:
            loc = page.get_by_text(text, exact=False)
            for i in range(min(loc.count(), 3)):
                if loc.nth(i).is_visible():
                    return False, f"页面出现登录提示「{text}」"
        except Exception:
            continue
    cookies = page.context.cookies()
    if not any(c.get("name", "").startswith("sessionid") for c in cookies):
        return False, "未检测到 sessionid Cookie"
    return True, "ok"


def rate_limited(page) -> str | None:
    """扫描可见的限流/验证提示,命中返回关键词。"""
    for keyword in RATE_LIMIT_KEYWORDS:
        try:
            loc = page.get_by_text(keyword, exact=False)
            for i in range(min(loc.count(), 5)):
                if loc.nth(i).is_visible():
                    return keyword
        except Exception:
            continue
    return None


# ---------------- 联系人定位 ----------------

def _conversation_visible(page, name: str) -> bool:
    """右侧会话头部(屏幕上半区)出现目标昵称才算切换成功。"""
    for exact in (True, False):
        try:
            loc = page.get_by_text(name, exact=exact)
            for i in range(loc.count()):
                box = loc.nth(i).bounding_box()
                if box and box.get("x", 0) > 300 and box.get("y", 0) < 120:
                    return True
        except Exception:
            continue
    return False


def _search_fallback(page, name: str) -> bool:
    """搜索兜底:列表里找不到时,用搜索框打开会话。"""
    try:
        box = page.get_by_placeholder("搜索", exact=False).first
        if box.count() == 0:
            return False
        box.click()
        box.fill(name)
        time.sleep(3.5)
        button = page.get_by_text("发消息", exact=False).first
        if button.count():
            button.click(force=True)
            time.sleep(3)
            return True
        hit = page.get_by_text(name, exact=True).first
        if hit.count() == 0:
            hit = page.get_by_text(name, exact=False).first
        if hit.count() == 0:
            return False
        hit.click(force=True)
        time.sleep(2.5)
        button = page.get_by_text("发消息", exact=False).first
        if button.count():
            button.click(force=True)
            time.sleep(2.5)
        return True
    except Exception as exc:
        logger.info("搜索打开 %s 失败: %s", name, exc)
        return False


def open_conversation(page, name: str, attempts: int = 5) -> bool:
    """点击目标好友并确认会话切换成功;失败时走搜索兜底。"""
    for _ in range(attempts):
        try:
            exact = page.get_by_text(name, exact=True)
            if exact.count():
                exact.first.click(force=True, timeout=10000)
                time.sleep(random.uniform(2, 4))
                if _conversation_visible(page, name):
                    return True
            else:
                page.mouse.move(220, 380)
                page.mouse.wheel(0, 500)
        except Exception as exc:
            logger.info("点击 %s 异常: %s", name, str(exc)[:100])
        time.sleep(random.uniform(1, 2))
    return _search_fallback(page, name) and _conversation_visible(page, name)


# ---------------- 消息输入与发送 ----------------

def _type_message(page, box, text: str) -> bool:
    """输入并回车发送,返回文字是否成功进入输入框。"""
    box.click()
    time.sleep(0.4)
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    time.sleep(0.3)
    for ch in text:
        page.keyboard.type(ch, delay=random.randint(60, 160))
    time.sleep(0.8)
    current = box.inner_text() or ""
    return text in current


def _wait_flushed(box, text: str, timeout: float = 8) -> bool:
    """发送成功后输入框应清空;用于确认消息真的发出去了。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        try:
            if text not in (box.inner_text() or ""):
                return True
        except Exception:
            pass
    return False


def send_message(page, text: str, dry_run: bool) -> tuple[bool, str]:
    """在当前会话发送消息,返回 (是否成功, 说明)。"""
    blocked = rate_limited(page)
    if blocked:
        return False, f"发送前检测到「{blocked}」"

    box = page.locator('div[contenteditable="true"]').first
    try:
        if box.count() == 0 or box.bounding_box() is None:
            return False, "找不到聊天输入框"
        box.wait_for(state="visible", timeout=8000)
    except Exception:
        return False, "找不到聊天输入框"

    if dry_run:
        return True, "演练模式,未实际发送"

    if not _type_message(page, box, text):
        return False, "文字未能输入输入框"
    page.keyboard.press("Enter")

    if _wait_flushed(box, text):
        return True, "ok"

    # 一次重试
    logger.warning("未检测到消息发出,重试一次")
    blocked = rate_limited(page)
    if blocked:
        return False, f"重试时检测到「{blocked}」"
    if not _type_message(page, box, text):
        return False, "重试时文字未能输入"
    page.keyboard.press("Enter")
    return (True, "ok") if _wait_flushed(box, text) else (False, "发送后输入框未清空,消息可能未发出")


def send_to(page, name: str, text: str, dry_run: bool) -> tuple[bool, str]:
    """完整发送流程:定位好友 → 校验切换 → 输入发送。"""
    if not open_conversation(page, name):
        return False, "未能切换到该好友会话(名字不在列表或页面结构变化)"
    blocked = rate_limited(page)
    if blocked:
        return False, f"检测到「{blocked}」"
    return send_message(page, text, dry_run)


# ---------------- 表情包(图片)发送 ----------------

# 聊天输入框旁的「图片」上传按钮,按命中概率排列候选选择器
_IMG_BTN_SELECTORS = (
    '[class*="chatInput"] [title*="图片"]',
    '[class*="chatInput"] [aria-label*="图片"]',
    'div[contenteditable="true"] ~ * [title*="图片"]',
    '[title="图片"]',
    '[aria-label="图片"]',
    '[class*="imageBtn"]',
    '[class*="ImageBtn"]',
    '[class*="uploadImage"]',
    '[class*="UploadImage"]',
    '[class*="imgIcon"]',
    '[class*="ImgIcon"]',
    '[class*="toolbar"] svg[class*="image"]',
)


def _find_image_button(page):
    for sel in _IMG_BTN_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def send_sticker(page, image_path, dry_run: bool) -> tuple[bool, str]:
    """点击聊天输入框的「图片」按钮上传表情包,返回 (是否成功, 说明)。"""
    import time as _t
    if dry_run:
        return True, "演练模式,未实际上传"
    try:
        btn = _find_image_button(page)
        if btn is None:
            return False, "未找到图片上传按钮(页面结构可能变化)"
        with page.expect_file_chooser(timeout=8000) as fc_info:
            btn.click(force=True)
        fc_info.value.set_files(str(image_path))
        _t.sleep(random.uniform(2.5, 4))  # 等待上传与自动发送
        return True, "ok"
    except Exception as exc:
        return False, f"表情包发送异常: {str(exc)[:120]}"


# ---------------- 联系人同步 ----------------

_EXTRACTOR_JS = r"""
() => {
    const out = [];
    const seen = new Set();
    const rows = document.querySelectorAll('[class*="conversationConversationItemwrapper"]');

    // 取标题文本并剔除标签/时间/火花等内嵌元素
    const cleanName = (el) => {
        const clone = el.cloneNode(true);
        clone.querySelectorAll(
            '[class*="TagNextToTitle"],[class*="timeStr"],[class*="streak"],[class*="Streak"],' +
            '[class*="badge"],[class*="commonStreak"],[class*="unread"],[class*="Unread"]'
        ).forEach(n => n.remove());
        return (clone.textContent || '').replace(/\s+/g, ' ').trim();
    };

    for (const row of rows) {
        const rect = row.getBoundingClientRect();
        if (rect.height < 30 || rect.width < 100) continue;

        // ---- 名字:title 元素 → aria-label → 整行兜底 ----
        let name = '';
        let titleEl = row.querySelector('.conversationConversationItemtitle')
                   || row.querySelector('[class*="Itemtitle"]');
        if (titleEl) name = cleanName(titleEl);
        if (!name) {
            const aria = (row.getAttribute('aria-label') || '').trim();
            if (aria) name = aria.split(/[,\n]/)[0].trim();
        }
        if (!name) name = cleanName(row);
        // 去掉可能混进来的 @账号名 尾巴
        name = name.replace(/\s*@[\w.\-]+$/, '').trim();
        if (!name || seen.has(name)) continue;
        if (/^\d+$/.test(name) || /^\d{1,2}:\d{2}$/.test(name)) continue;
        if (name === '消息' || name === '私信' || name === '朋友私信' || name === '通知') continue;
        if (name.length > 40) continue;
        seen.add(name);

        // ---- 账号名(抖音号,灰字,可选) ----
        let account = '';
        const sub = row.querySelector('[class*="ItemsubTitle"],[class*="subtitle"],[class*="Subtitle"]');
        const subText = sub ? (sub.textContent || '') : '';
        const mAcc = subText.match(/@([\w.\-]{2,})/) || (row.textContent || '').match(/@([\w.\-]{2,})/);
        if (mAcc) account = mAcc[1];

        // ---- 火花天数:优先 commonStreak 徽章文本,再回退 🔥 正则 ----
        let days = 0;
        const st = row.querySelector('[class*="commonStreak"],[class*="streakContainer"],[class*="Streak"]');
        if (st) {
            const mD = (st.textContent || '').match(/\d+/);
            if (mD) days = parseInt(mD[0], 10);
        }
        if (!days) {
            const mD2 = (row.textContent || '').match(/🔥\s*(\d+)/);
            if (mD2) days = parseInt(mD2[1], 10);
        }

        // ---- 头像:优先 ≥32px 的真实头像图,排除火焰图标 ----
        let avatar = '';
        const imgs = row.querySelectorAll('img');
        for (const img of imgs) {
            const src = img.src || '';
            if (!src || src.includes('flame')) continue;
            const r2 = img.getBoundingClientRect();
            const size = r2.width || img.naturalWidth || 0;
            if (size >= 32) { avatar = src; break; }
        }
        if (!avatar) {
            for (const img of imgs) {
                const src = img.src || '';
                if (src && !src.includes('flame')) { avatar = src; break; }
            }
        }

        out.push({ name, days, avatar, account });
    }
    let atBottom = false;
    try {
        const scroller = document.querySelector('[class*="conversationList"],[class*="chatList"],[class*="ContactList"]');
        const el = (scroller && scroller.scrollHeight > scroller.clientHeight) ? scroller : document.scrollingElement;
        atBottom = el ? (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) : true;
    } catch (e) {}
    return { items: out, atBottom };
}
"""


def fetch_conversations(page, max_rounds: int = 20) -> list[dict]:
    """滚动聊天列表并提取联系人(带触底/停滞检测,避免无限滚动)。"""
    collected: list[dict] = []
    stable = 0
    for _ in range(max_rounds):
        try:
            result = page.evaluate(_EXTRACTOR_JS) or {}
        except Exception:
            result = {}
        items = result.get("items") or []
        new = [x for x in items if x not in collected]
        if new:
            collected.extend(new)
            stable = 0
        else:
            stable += 1
            if stable >= 2 or result.get("atBottom"):
                break
        if result.get("atBottom"):
            break
        try:
            page.mouse.move(220, 380)
            page.mouse.wheel(0, 450)
        except Exception:
            pass
        time.sleep(0.35)
    return collected


def open_chat(page, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            page.goto(CHAT_URL, timeout=90000, wait_until="domcontentloaded")
            return True
        except Exception as exc:
            logger.info("打开聊天页失败(第 %s 次): %s", attempt + 1, str(exc)[:80])
            time.sleep(5)
    return False


def sync_friends_page(account_id: str, headless: bool = True, max_rounds: int = 20) -> dict:
    """打开私信页同步联系人列表,返回 {names, error}。"""
    result: dict = {"names": [], "error": None}
    state = account_dir(account_id) / "state.json"
    if not state.exists():
        result["error"] = "该账号尚未上传登录态 state.json"
        return result
    try:
        with open_session(storage_state=state, headless=headless) as (pw, browser, context, page):
            if not open_chat(page):
                result["error"] = "无法打开抖音私信页面"
                return result
            page.wait_for_timeout(3000)
            logged, why = check_login(page)
            if not logged:
                result["error"] = why
                return result
            collected: list[dict] = []
            for _ in range(3):
                try:
                    page.wait_for_selector(".conversationConversationItemtitle", timeout=45000)
                except Exception:
                    pass
                # 行渲染后火花徽章等元素是异步补全的,多等几秒再提取
                page.wait_for_timeout(4000)
                collected = fetch_conversations(page, max_rounds)
                if len(collected) >= 3:
                    break
                try:
                    page.reload(wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_timeout(10000)
                except Exception:
                    break
            result["names"] = collected
            logger.info("[%s] 同步联系人 %s 个", account_id, len(collected))
    except Exception as exc:
        logger.error("[%s] 同步联系人异常: %s", account_id, exc)
        result["error"] = f"同步联系人异常: {exc}"
    return result


def run_send_page(account_id: str, targets: list[dict], dry_run: bool,
                  headless: bool = True, gap: tuple[int, int] = (6, 12)) -> dict:
    """主发送流程:打开私信页 → 逐个定位发送。返回结果字典。"""
    result: dict = {"ok": [], "failed": [], "skipped": [], "logged_out": False, "rate_limited": False}
    state = account_dir(account_id) / "state.json"
    if not state.exists():
        result["logged_out"] = True  # 与过期同路径:触发登录态失效微信推送
        result["failed"].append({"name": "_system", "reason": "该账号尚未上传登录态 state.json"})
        return result
    try:
        with open_session(storage_state=state, headless=headless) as (pw, browser, context, page):
            if not open_chat(page):
                result["failed"].append({"name": "_system", "reason": "无法打开抖音私信页面"})
                return result
            time.sleep(8)
            logged, why = check_login(page)
            if not logged:
                result["logged_out"] = True
                result["failed"].append({"name": "_system", "reason": why})
                _save_error_shot(page, account_id)
                return result
            logger.info("[%s] 待发送 %s 人, dry=%s", account_id, len(targets), dry_run)
            for entry in targets:
                name = entry["name"]
                text = entry.get("text", "🔥")
                ok, reason = send_to(page, name, text, dry_run)
                if ok:
                    result["ok"].append(name)
                    logger.info("[%s] 已发送 %s: %s", account_id, name, "(演练)" if dry_run else text)
                    # 随机表情包:文字发出后追加,失败不影响本轮成功判定
                    sticker = entry.get("sticker")
                    if sticker:
                        if dry_run:
                            logger.info("[%s] (演练)将追加表情包 %s → %s", account_id, Path(sticker).name, name)
                        else:
                            time.sleep(random.uniform(1.5, 3))
                            sok, sreason = send_sticker(page, sticker, dry_run)
                            if sok:
                                logger.info("[%s] 已追加表情包 → %s", account_id, name)
                            else:
                                logger.warning("[%s] 表情包发送失败(%s): %s", account_id, name, sreason)
                else:
                    result["failed"].append({"name": name, "reason": reason})
                    logger.warning("[%s] 发送 %s 失败: %s", account_id, name, reason)
                    blocked = rate_limited(page)
                    if blocked:
                        result["rate_limited"] = True
                        logger.warning("[%s] 触发限流「%s」,本轮停止", account_id, blocked)
                        break
                time.sleep(random.uniform(gap[0], gap[1]))
    except Exception as exc:
        logger.error("[%s] 运行异常: %s", account_id, exc)
        result["failed"].append({"name": "_system", "reason": f"运行异常: {exc}"})
    return result
