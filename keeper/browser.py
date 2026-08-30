"""浏览器会话管理:统一启动 Chromium、注入反自动化指纹、控制并发名额。

- 全局信号量限制同时存活的浏览器数量(默认 5),防止多账号并发开太多浏览器;
- 优先尝试 playwright-stealth 隐藏自动化痕迹(可选依赖);
- 固定中文环境与上海时区,降低被风控误判的概率;
- 提供 contextmanager,退出时确保浏览器与 playwright 实例都被回收。
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger("spark")

MAX_BROWSERS = 5
_slots = threading.BoundedSemaphore(MAX_BROWSERS)

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def slots_available() -> int:
    return max(0, int(_slots._value))  # noqa: SLF001 仅用于状态展示


def launch_browser(pw, headless: bool = True, extra_args: list[str] | None = None):
    """启动浏览器,自动回退:默认 Chromium → 系统 Edge → 系统 Chrome。

    这样 Windows 用户即使不下载 Playwright 的 Chromium(网络受限时),
    也能直接复用系统自带的 Edge 内核,开箱即用。
    全部失败时抛出最后一个异常。
    """
    args = list(_LAUNCH_ARGS) + (extra_args or [])
    last_error: Exception | None = None
    try:
        return pw.chromium.launch(headless=headless, args=args)
    except Exception as exc:  # noqa: BLE001
        last_error = exc
    for channel in ("msedge", "chrome"):
        try:
            return pw.chromium.launch(channel=channel, headless=headless, args=args)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise last_error or RuntimeError("无法启动任何浏览器")


def _apply_stealth(page) -> None:
    """尝试注入 stealth 脚本;失败静默(非致命)。"""
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except Exception:
            pass


@contextmanager
def open_session(storage_state: Path | str | None = None, headless: bool = True, viewport: tuple[int, int] | None = None):
    """打开一个浏览器会话,产出 (playwright, browser, context, page)。

    退出 with 块时自动关闭全部资源并释放并发名额。
    """
    state_file = str(storage_state) if storage_state and Path(storage_state).exists() else None
    _slots.acquire()
    pw = sync_playwright().start()
    browser = None
    try:
        browser = launch_browser(pw, headless=headless)
        context = browser.new_context(
            viewport={"width": viewport[0] if viewport else 1366, "height": viewport[1] if viewport else 768},
            user_agent=_USER_AGENT,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
            storage_state=state_file,
        )
        page = context.new_page()
        _apply_stealth(page)
        yield pw, browser, context, page
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass
        _slots.release()
