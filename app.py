"""Spark Cloud 服务入口:Flask Web 后台 + 调度器 + 实例锁。

启动时:
1. 初始化数据目录与默认账号;
2. 生成/读取访问令牌;
3. 启动定时调度线程(Planner);
4. 单实例自检:若已有一个活跃实例在运行则拒绝启动,防止重复发送。
"""
from __future__ import annotations

import atexit
import json
import os
import socket
import sys
from pathlib import Path

# Windows 控制台 UTF-8 兼容
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import Flask, Response, request, send_from_directory

from keeper import __version__, accounts as acc_store, logs as logstore, planner, runner
from keeper import web as web_api
from keeper.settings import BASE_DIR, DATA, LOCK_FILE, DEFAULT_ACCOUNT, access_token, account_dir

logger = logstore.setup()
STATIC_DIR = BASE_DIR / "static"


# ---------------- 单实例锁 ----------------

def _proc_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in r.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _proc_starttime(pid: int) -> str:
    """POSIX 下读取进程启动时间(第 22 个字段),用于识别 PID 复用。"""
    if os.name == "nt":
        return ""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19]
    except Exception:
        return ""


def _acquire_instance_lock() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    host = socket.gethostname()
    start = _proc_starttime(os.getpid())
    if LOCK_FILE.exists():
        try:
            old = json.loads(LOCK_FILE.read_text())
            old_pid = int(old.get("pid", 0))
            old_host = str(old.get("host", ""))
            old_start = str(old.get("start", ""))
        except Exception:
            old_pid = old_host = old_start = None
        if old_pid and old_host == host and _proc_alive(old_pid) and old_start and _proc_starttime(old_pid) == old_start:
            logger.error("检测到已有 Spark Cloud 实例在运行(PID %s),拒绝启动,请先停止旧实例", old_pid)
            sys.exit("已有实例在运行,请先停止旧实例")
        logger.info("旧实例锁已失效,接管")
    LOCK_FILE.write_text(json.dumps({"pid": os.getpid(), "host": host, "start": start}), encoding="utf-8")
    atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))


# ---------------- Flask 应用 ----------------

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.register_blueprint(web_api.api)


@app.get("/")
def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    token = access_token()
    inject = f'<script>window.__SERVER_AUTH_TOKEN__ = "{token}";</script>'
    if "</head>" in html:
        html = html.replace("</head>", f"  {inject}\n</head>")
    return Response(html, mimetype="text/html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/avatars/<path:filename>")
def avatars(filename: str):
    root = (DATA / "avatars").resolve()
    target = (root / filename).resolve()
    if not str(target).startswith(str(root)):
        return Response("forbidden", status=403)
    return send_from_directory(root, filename)


@app.get("/bg/<path:filename>")
def bg_file(filename: str):
    """自定义背景图片(data/bg/ 下,重启/刷新不丢失)。"""
    root = (DATA / "bg").resolve()
    target = (root / filename).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return Response("not found", status=404)
    return send_from_directory(root, filename)


@app.get("/stickers/<account_id>/<path:filename>")
def sticker_file(account_id: str, filename: str):
    """账号表情包图片(data/accounts/<id>/stickers/)。"""
    root = (account_dir(account_id) / "stickers").resolve()
    target = (root / filename).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return Response("not found", status=404)
    return send_from_directory(root, filename)


@app.after_request
def no_cache(response):
    p = request.path
    if p.startswith("/static/") or p == "/" or p.startswith("/avatars/") or p.startswith("/stickers/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# ---------------- 启动与收尾 ----------------

def bootstrap() -> None:
    _acquire_instance_lock()
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "accounts").mkdir(parents=True, exist_ok=True)
    (DATA / "avatars").mkdir(parents=True, exist_ok=True)
    acc_store.list_accounts()  # 确保默认账号可见

    token = access_token()
    if token:
        logger.info("网页访问令牌已就绪(通过 X-Token 请求头携带)")

    planner.attach(
        on_run=lambda account_id: runner.run_once(account_id, dry=False, auto=True),
        on_harvest=lambda account_id: runner.run_scan(account_id),
    )
    planner.apply_all()
    planner.start()

    # 微信 Bot:已绑定则随启动立即拉起监听线程。
    # 否则只有打开设置页才会懒加载,重启后微信发消息会一直无响应。
    try:
        from keeper import wxbot as _wxmod
        _b = _wxmod.init_wxbot(DATA)
        if _b.s.get("bot_token"):
            logger.info("微信 Bot 已绑定,监听线程随启动拉起")
        else:
            logger.info("微信 Bot 未绑定,请在设置页扫码绑定")
    except Exception as e:  # noqa: BLE001
        logger.info("微信 Bot 初始化跳过: %s", e)


def main() -> None:
    bootstrap()
    host = os.environ.get("SPARK_HOST", os.environ.get("HOST", "0.0.0.0"))
    port = int(os.environ.get("SPARK_PORT", os.environ.get("PORT", "8000")))
    logger.info("Spark Cloud v%s 启动,管理后台: http://%s:%s", __version__, host, port)
    if host in ("0.0.0.0", ""):
        # 额外挂一个 IPv6 监听(Windows 下 v6-only 与 v4 监听不冲突):
        # 手机流量有公网 IPv6 时可直达,微信推送的二维码链接在外网也能打开
        import threading as _th

        def _serve_v6():
            try:
                from werkzeug.serving import make_server
                make_server("::", port, app, threaded=True).serve_forever()
            except Exception as e:  # noqa: BLE001
                logger.info("IPv6 监听未启用: %s", e)

        _th.Thread(target=_serve_v6, daemon=True).start()
    try:
        from werkzeug.serving import run_simple
        run_simple(host, port, app, threaded=True, use_reloader=False)
    finally:
        planner.shutdown()


if __name__ == "__main__":
    main()
