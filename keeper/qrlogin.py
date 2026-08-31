"""网页扫码登录:在服务器/远端直接打开抖音登录页,生成二维码供手机扫码。

流程:
1. start(account_id)  -> 为账号启动独立扫码会话(后台线程,受全局并发名额约束);
2. poll(account_id)   -> 前端轮询:返回状态与二维码(data URL);
3. 检测到登录 Cookie  -> 自动导出 storage_state 覆盖该账号 state.json,销毁浏览器;
4. cancel(account_id) -> 手动取消;超时(默认 5 分钟)自动回收,防止浏览器泄漏。

同一账号同时只允许一个扫码会话;不同账号可并行(受全局名额限制)。
"""
from __future__ import annotations

import base64
import logging
import random
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

import requests
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # Termux/手机等无浏览器引擎环境:后台可启动,仅扫码登录不可用
    HAS_PLAYWRIGHT = False
    sync_playwright = None

from .browser import _slots  # 复用全局并发名额
from .settings import account_dir
from .storage import write_text

logger = logging.getLogger("spark")

CHAT_URL = "https://www.douyin.com/chat?isPopup=1"
SESSION_TIMEOUT = 300          # 扫码总等待(秒)
QR_REFRESH_LIMIT = 5           # 二维码自动刷新上限
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}
EXPIRED_TEXTS = ["二维码已过期", "已失效", "已过期", "点击刷新", "刷新"]

_sessions: dict[str, dict] = {}
_stop_flags: dict[str, threading.Event] = {}
_guard = threading.Lock()


def _public(state: dict) -> dict:
    return {
        "status": state["status"],
        "message": state["message"],
        "qrcode": state.get("qrcode") if state["status"] == "waiting" else "",
        "error": state.get("error", ""),
    }


def _update(account_id: str, **fields) -> None:
    with _guard:
        state = _sessions.get(account_id)
        if state is None:
            return
        state.update(fields)
        state["last_active"] = time.time()


def start(account_id: str) -> dict:
    """发起扫码会话(幂等:已有活跃会话则直接返回)。"""
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("此环境未安装 playwright(手机/Termux 无浏览器引擎),无法扫码登录;请在电脑上运行 python app.py 完成扫码")
    with _guard:
        current = _sessions.get(account_id)
        if current and current["status"] in ("preparing", "waiting"):
            return {"ok": True, "resumed": True, **_public(current)}
        flag = threading.Event()
        _stop_flags[account_id] = flag
        state = {"status": "preparing", "message": "正在启动扫码环境…", "qrcode": "", "error": "", "started_at": time.time(), "last_active": time.time(), "qr_token": secrets.token_urlsafe(12)}
        _sessions[account_id] = state

    worker = threading.Thread(target=_worker, args=(account_id, flag), daemon=True)
    worker.start()
    # 硬超时保护:工作线程卡死时强制终态并释放名额
    watchdog = threading.Timer(SESSION_TIMEOUT + 90, lambda: _hard_expire(account_id))
    watchdog.daemon = True
    watchdog.start()
    logger.info("[%s] 网页扫码会话已启动", account_id)
    return {"ok": True, "resumed": False, **_public(state)}


def poll(account_id: str) -> dict:
    with _guard:
        state = _sessions.get(account_id)
        if not state:
            return {"status": "idle", "message": "", "qrcode": "", "error": ""}
        return _public(state)


def qr_token(account_id: str) -> str:
    """当前会话二维码页的访问令牌(无会话返回空串)。"""
    with _guard:
        state = _sessions.get(account_id)
        return (state or {}).get("qr_token", "")


def _decode_qr_img(img) -> str:
    """尽力解码二维码图片:pyzbar 优先(对真实小码/窄静区宽容得多),
    失败后走 cv2 原图→灰度→2/3/4 倍放大→二值化 多轮重试。"""
    # 1) pyzbar(Windows 轮子自带 zbar DLL;接受 2-D ndarray)
    try:
        from pyzbar.pyzbar import decode as _zbar_decode
        candidates = []
        try:
            import cv2
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            candidates = [gray] + [
                cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
                for s in (2, 3)]
        except Exception:  # noqa: BLE001
            candidates = [img]
        for cand in candidates:
            try:
                res = _zbar_decode(cand)
            except Exception:  # noqa: BLE001 zbar 不可用,跳到 cv2
                break
            for d in (res or []):
                txt = (getattr(d, "data", b"") or b"").decode("utf-8", "ignore").strip()
                if txt:
                    return txt
    except Exception:  # noqa: BLE001 未安装 pyzbar → 纯 cv2 路径
        pass

    # 2) cv2 兜底
    import cv2

    det = cv2.QRCodeDetector()
    try:
        txt, _, _ = det.detectAndDecode(img)
        txt = (txt or "").strip()
        if txt:
            return txt
    except Exception:  # noqa: BLE001
        pass
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except Exception:  # noqa: BLE001
        return ""
    for scale in (2, 3, 4):
        try:
            big = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        except Exception:  # noqa: BLE001
            continue
        for variant in (big,
                        cv2.adaptiveThreshold(big, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                              cv2.THRESH_BINARY, 31, 5)):
            try:
                txt, _, _ = det.detectAndDecode(variant)
                txt = (txt or "").strip()
                if txt:
                    return txt
            except Exception:  # noqa: BLE001
                pass
    return ""


def qr_content(account_id: str) -> str:
    """二维码图片里编码的内容串(确认链接),解码失败返回空串。

    抖音对"相册识别登录码"有风控,把码里的确认链接直接发给用户点开,
    可以完全绕开扫码;这里惰性解码并缓存到会话状态。
    """
    with _guard:
        state = _sessions.get(account_id)
    if state is None:
        return ""
    cached = state.get("qr_content") or ""
    if cached:
        return cached
    data_url = state.get("qrcode") or ""
    if not data_url.startswith("data:image"):
        return ""
    try:
        import cv2
        import numpy as np

        raw = base64.b64decode(data_url.partition(",")[2])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        txt = _decode_qr_img(img) if img is not None else ""
    except Exception as e:  # noqa: BLE001 解码失败不阻塞推送
        logger.info("二维码内容解码失败: %s", e)
        return ""
    if txt:
        _update(account_id, qr_content=txt)
    return txt


def cancel(account_id: str) -> dict:
    with _guard:
        state = _sessions.get(account_id)
        if not state or state["status"] in ("done", "failed", "expired", "canceled"):
            _sessions.pop(account_id, None)
            return {"ok": True, "message": "无进行中的扫码会话"}
        flag = _stop_flags.get(account_id)
    if flag:
        flag.set()
    for _ in range(30):
        time.sleep(0.1)
        with _guard:
            current = _sessions.get(account_id)
            if not current or current["status"] not in ("preparing", "waiting"):
                break
    else:
        with _guard:
            current = _sessions.get(account_id)
            if current and current["status"] == "waiting":
                current["status"] = "canceled"
                current["message"] = "已取消"
    return {"ok": True, "message": "已取消"}


def _hard_expire(account_id: str) -> None:
    """超时兜底:强制标记终态,防止浏览器进程泄漏。"""
    flag = _stop_flags.get(account_id)
    if flag:
        flag.set()
    with _guard:
        state = _sessions.get(account_id)
        if state and state["status"] in ("preparing", "waiting"):
            state.update(status="expired", message="扫码超时,请重新发起", qrcode="", error="")
            logger.warning("[%s] 扫码会话触发硬超时保护", account_id)


# ---------------- 工作线程 ----------------

def _launch_browser(pw):
    """优先在 Xvfb 虚拟屏幕跑有头内核(有头比无头更不易被识别);无 Xvfb 则无头。"""
    common = dict(
        args=[
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--disable-blink-features=AutomationControlled",
            "--disable-extensions", "--mute-audio",
        ],
        ignore_default_args=["--enable-automation"],
    )
    xvfb = shutil.which("Xvfb")
    if xvfb:
        for _ in range(4):
            display = f":{random.randint(90, 180)}"
            try:
                proc = subprocess.Popen(
                    [xvfb, display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(0.8)
                if proc.poll() is not None:
                    continue
                try:
                    browser = pw.chromium.launch(headless=False, env={"DISPLAY": display}, **common)
                    return browser, proc
                except Exception:
                    proc.terminate()
            except Exception:
                continue
    # 无 Xvfb:依次回退 Chromium(无头) → 系统 Edge → 系统 Chrome
    last_error: Exception | None = None
    try:
        return pw.chromium.launch(headless=True, **common), None
    except Exception as exc:  # noqa: BLE001
        last_error = exc
    for channel in ("msedge", "chrome"):
        try:
            return pw.chromium.launch(channel=channel, headless=True, **common), None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise last_error or RuntimeError("无法启动任何浏览器")


def _worker(account_id: str, stop_flag: threading.Event) -> None:
    pw = None
    browser = None
    xvfb_proc = None
    try:
        _slots.acquire()
        try:
            if stop_flag.is_set():
                raise _Canceled()
            _update(account_id, status="preparing", message="正在打开抖音登录页…")
            pw = sync_playwright().start()
            browser, xvfb_proc = _launch_browser(pw)
            major = (browser.version or "").split(".")[0] or "124"
            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.goto(CHAT_URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            _click_login_tab(page)

            qr = _wait_qrcode(page)
            if not qr:
                raise RuntimeError("未能提取到登录二维码,请重试")
            _update(account_id, status="waiting", message="请使用抖音 App 扫码登录", qrcode=qr)

            deadline = time.time() + SESSION_TIMEOUT
            refreshes = 0
            face_mode = False
            last_face_qr = ""
            while time.time() < deadline:
                if stop_flag.is_set():
                    raise _Canceled()
                if _logged_in(context):
                    _export_state(context, account_id)
                    _update(account_id, status="done", message="登录成功,登录态已保存")
                    logger.info("[%s] 网页扫码登录成功", account_id)
                    return

                if _qr_expired(page):
                    refreshes += 1
                    if refreshes > QR_REFRESH_LIMIT:
                        raise RuntimeError("二维码刷新次数过多,请重新发起")
                    _click_refresh(page)
                    page.wait_for_timeout(2500)
                    new_qr = _wait_qrcode(page, timeout_ms=30000)
                    if new_qr:
                        _update(account_id, qrcode=new_qr, message=f"二维码已自动刷新(第 {refreshes} 次)",
                                qr_content="")

                # 二次安全验证(刷脸):页面可能出现新二维码
                if not face_mode and _js_click(page, ["手机刷脸验证", "刷脸验证"]):
                    face_mode = True
                    _update(account_id, message="触发安全验证:请扫描页面上的新二维码")
                    page.wait_for_timeout(3000)
                elif face_mode:
                    _js_click(page, ["已完成", "验证成功"])
                    face_qr = _scan_for_qr_image(page)
                    if face_qr and face_qr != last_face_qr:
                        last_face_qr = face_qr
                        # 新码=新内容:旧确认链接缓存必须失效,
                        # 防止误推已失效的登录链接(点开就是「该二维码状态错误」)
                        _update(account_id, qrcode=face_qr, qr_content="")

                page.wait_for_timeout(1500)

            _update(account_id, status="expired", message="扫码超时,请重新发起", qrcode="")
        finally:
            _slots.release()
    except _Canceled:
        _update(account_id, status="canceled", message="已取消", qrcode="")
    except Exception as exc:
        msg = str(exc)[:200]
        _update(account_id, status="failed", message="扫码会话异常", error=msg, qrcode="")
        logger.warning("[%s] 扫码会话异常: %s", account_id, msg)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        if xvfb_proc:
            try:
                xvfb_proc.terminate()
            except Exception:
                pass
        _stop_flags.pop(account_id, None)
        threading.Timer(120, lambda: _sessions.pop(account_id, None)).start()


class _Canceled(Exception):
    pass


# ---------------- 页面操作 ----------------

def _click_login_tab(page) -> None:
    """收起面板残留并切到「扫码登录」标签。"""
    for attempt in (
        lambda: page.get_by_text("扫码登录", exact=False).first.click(timeout=1500),
        lambda: page.locator("#animate_qrcode_container").first.click(timeout=1500),
    ):
        try:
            attempt()
            page.wait_for_timeout(1200)
        except Exception:
            pass


def _qr_expired(page) -> bool:
    for text in EXPIRED_TEXTS:
        try:
            loc = page.get_by_text(text, exact=False)
            for i in range(min(loc.count(), 3)):
                if loc.nth(i).is_visible():
                    return True
        except Exception:
            continue
    return False


def _click_refresh(page) -> None:
    for selector in ("#animate_qrcode_container", 'div[class*="qrcode"]', 'div[class*="refresh"]'):
        try:
            loc = page.locator(selector)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                return
        except Exception:
            continue
    try:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception:
        pass


def _js_click(page, texts: list[str]) -> bool:
    for text in texts:
        try:
            loc = page.get_by_text(text, exact=False)
            if loc.count():
                loc.first.evaluate("el => el.click()")
                return True
        except Exception:
            continue
    return False


_FIND_QR_JS = """
() => {
    const pick = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 100 || r.width > 380 || Math.abs(r.width - r.height) > 20) return null;
        const src = el.src || '';
        if (src.startsWith('data:image')) return src;
        try {
            const c = document.createElement('canvas');
            c.width = el.naturalWidth || r.width;
            c.height = el.naturalHeight || r.height;
            c.getContext('2d').drawImage(el, 0, 0, c.width, c.height);
            return c.toDataURL('image/png');
        } catch (e) { return null; }
    };
    const imgs = document.querySelectorAll('img');
    for (let i = imgs.length - 1; i >= 0; i--) { const v = pick(imgs[i]); if (v) return v; }
    const cvs = document.querySelectorAll('canvas');
    for (let j = cvs.length - 1; j >= 0; j--) {
        const r = cvs[j].getBoundingClientRect();
        if (r.width >= 100 && r.width <= 380 && Math.abs(r.width - r.height) <= 20) {
            try { return cvs[j].toDataURL('image/png'); } catch (e) {}
        }
    }
    return null;
}
"""


def _scan_for_qr_image(page) -> str | None:
    """按「近方形大图」启发式扫描页面中的二维码(登录面板或验证弹窗)。"""
    try:
        data = page.evaluate(_FIND_QR_JS)
        return data if data and str(data).startswith("data:image") else None
    except Exception:
        return None


def _wait_qrcode(page, timeout_ms: int = 45000) -> str | None:
    """等待二维码出现并转成 data URL;最终以整页截图兜底。"""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for frame in (page.main_frame, *page.frames):
            try:
                loc = frame.locator("#animate_qrcode_container img")
                if loc.count() and loc.first.is_visible():
                    src = loc.first.get_attribute("src") or ""
                    if len(src) > 50:
                        return _to_data_url(src)
            except Exception:
                continue
        time.sleep(0.8)
    shot = _page_screenshot(page)
    return shot


def _to_data_url(src: str) -> str:
    if src.startswith("data:image"):
        return src
    if src.startswith("http"):
        try:
            resp = requests.get(src, timeout=8)
            return "data:image/png;base64," + base64.b64encode(resp.content).decode()
        except Exception:
            pass
    return "data:image/png;base64," + src


def _page_screenshot(page) -> str | None:
    for _ in range(2):
        try:
            shot = page.screenshot(timeout=8000)
            return "data:image/png;base64," + base64.b64encode(shot).decode()
        except Exception:
            try:
                page.wait_for_timeout(1500)
            except Exception:
                break
    return None


def _logged_in(context) -> bool:
    try:
        cookies = context.cookies("https://www.douyin.com")
        return any(c.get("name") in LOGIN_COOKIES and c.get("value") for c in cookies)
    except Exception:
        return False


def _export_state(context, account_id: str) -> None:
    state = context.storage_state()
    if not isinstance(state, dict):
        state = {"cookies": [], "origins": []}
    state.setdefault("cookies", [])
    state.setdefault("origins", [])
    path: Path = account_dir(account_id) / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    write_text(path, json.dumps(state, ensure_ascii=False))
    logger.info("[%s] 登录态已写入 %s", account_id, path)
    try:
        from . import runtime as _rt

        _rt.save(account_id, session_status="ok")
    except Exception:  # 后台未运行时也能静默通过
        pass
