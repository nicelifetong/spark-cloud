"""本地登录态提取工具:在自己电脑上弹出浏览器扫码,生成 state.json。

- 浏览器自动回退:Playwright Chromium → 系统 Edge → 系统 Chrome,无需额外下载;
- 适合第一次使用(个人电脑网络风控最宽松),以及云端凭证过期后重新扫码。
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from keeper.settings import BASE_DIR, account_dir

STATE_TARGET = account_dir("default") / "state.json"
ROOT_COPY = BASE_DIR / "state.json"
LOGIN_COOKIES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}


def main() -> None:
    print("=" * 64)
    print("  Spark Cloud · 提取抖音登录态")
    print("=" * 64)
    print("1. 稍后弹出浏览器并打开抖音;")
    print("2. 在页面右上角登录(手机 App 扫码 或 短信);")
    print("3. 登录成功后自动保存登录态(最长等待 5 分钟)。")
    print("=" * 64)
    STATE_TARGET.parent.mkdir(parents=True, exist_ok=True)

    # 延迟导入:依赖缺失时给出友好提示,而不是裸 traceback
    try:
        from playwright.sync_api import sync_playwright
        from keeper.browser import launch_browser
    except ImportError:
        print("[错误] 缺少 Playwright,请先在项目目录执行:")
        print("    pip install -r requirements.txt")
        print("    playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        try:
            browser = launch_browser(pw, headless=False)
        except Exception as exc:
            print(f"[错误] 启动浏览器失败:{exc}")
            print("    Windows 用户请确认已安装 Microsoft Edge;")
            print("    或执行: playwright install chromium 后重试。")
            sys.exit(1)

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        try:
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            print("[提示] 打开页面稍慢,请直接在浏览器中操作")

        print("[*] 请在浏览器中登录抖音账号(最长等待 5 分钟)…")
        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                cookies = context.cookies()
            except Exception:
                cookies = []
            if any(c.get("name") in LOGIN_COOKIES and c.get("value") for c in cookies):
                time.sleep(2)
                context.storage_state(path=str(STATE_TARGET))
                try:
                    shutil.copy2(STATE_TARGET, ROOT_COPY)
                except Exception:
                    pass
                print("")
                print("=" * 64)
                print("  登录态提取成功!")
                print(f"  [OK] {STATE_TARGET}")
                print(f"  [OK] 副本 {ROOT_COPY}")
                print("=" * 64)
                print("下一步:双击 scripts/3.启动管理后台.bat 本地使用,或")
                print("       在网页后台「凭证」页上传 / 运行 scripts/4.同步登录态到服务器.bat。")
                browser.close()
                return
            time.sleep(1.5)

        print("[错误] 5 分钟内未检测到登录,请重新运行。")
        browser.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
