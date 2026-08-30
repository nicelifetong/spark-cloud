"""REST API(Flask Blueprint):账号管理、配置、好友、任务、扫码、日志。

鉴权:请求头 X-Token(未配置令牌时不校验)。
约定:多账号接口一律使用路径参数 /api/accounts/<account_id>/...,
每个账号独立配置、台账与任务,互不干扰。
"""
from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from . import __version__, accounts as acc_store, ledger as book, qrlogin, runner, planner
from . import auth as web_auth, logs as logstore, runtime as rt
from . import stickers as sticker_store
from . import history as history_store
from . import notify as notify_store
from .settings import (
    BASE_DIR,
    DATA,
    DEFAULT_ACCOUNT,
    DEFAULT_CONFIG,
    _in_docker,
    access_token,
    account_dir,
    port_locked,
    saved_web_port,
    set_web_port,
    web_port,
)

logger = logging.getLogger("spark")

api = Blueprint("api", __name__, url_prefix="/api")


# ---------------- Web 登录(账号系统) ----------------

@api.before_request
def _require_web_login():
    """启用登录账号后,除登录/状态接口外所有 API 都要求有效会话。"""
    if request.path.startswith("/api/auth/status") or request.path.startswith("/api/auth/login"):
        return None
    if request.path.startswith("/api/qrpub/"):
        return None  # 微信推送的二维码页:用会话令牌自鉴权,免网页登录
    if web_auth.enabled() and not web_auth.check_session(request.headers.get("X-Session", "")):
        return jsonify({"detail": "请先登录"}), 401
    return None


@api.get("/auth/status")
def auth_status():
    sess = request.headers.get("X-Session", "")
    return {
        "ok": True,
        "enabled": web_auth.enabled(),
        "logged_in": web_auth.check_session(sess) if web_auth.enabled() else False,
        "username": web_auth.username(),
    }


@api.post("/auth/login")
def auth_login():
    body = request.get_json(silent=True) or {}
    user = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if web_auth.verify(user, password):
        return {"ok": True, "token": web_auth.create_session(), "username": user}
    return jsonify({"detail": "用户名或密码不正确"}), 401


@api.post("/auth/logout")
def auth_logout():
    web_auth.destroy_session(request.headers.get("X-Session", ""))
    return {"ok": True}


@api.post("/auth/setup")
def auth_setup():
    """设置/更新登录账号。未启用登录时可直接设置;已启用则必须登录后修改。"""
    if web_auth.enabled() and not web_auth.check_session(request.headers.get("X-Session", "")):
        return jsonify({"detail": "请先登录后再修改账号"}), 401
    body = request.get_json(silent=True) or {}
    if body.get("disable"):
        web_auth.disable()
        return {"ok": True, "enabled": False}
    user = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not user or len(user) > 32:
        return jsonify({"detail": "用户名不能为空且不超过 32 个字符"}), 400
    if len(password) < 4:
        return jsonify({"detail": "密码至少 4 位"}), 400
    web_auth.setup(user, password, enable=True)
    return {"ok": True, "enabled": True, "username": user}


# ---------------- 鉴权 ----------------

def _unauthorized() -> Response:
    return jsonify({"detail": "访问令牌不正确"}), 401


def _check_auth() -> bool:
    token = access_token()
    if not token:
        return True
    got = request.headers.get("X-Token", "")
    return got == token


def _require_auth():
    if not _check_auth():
        return _unauthorized()
    return None


def _resolve(account_id: str) -> tuple[str, Response | None]:
    aid = (account_id or DEFAULT_ACCOUNT).strip()
    if not acc_store.exists(aid):
        return aid, (jsonify({"detail": f"账号不存在:{aid}"}), 404)
    return aid, None


def _account_summary(a: dict) -> dict:
    aid = a["id"]
    r = rt.load(aid)
    busy = runner.is_busy(aid)
    return {
        **a,
        "session_status": r.get("session_status", "unknown"),
        "running": r.get("running", False),
        "last_run": r.get("last_run"),
        "next_run": _planner_next(aid),
        "next_harvest": _planner_harvest(aid),
        "contacts_fetching": busy,
        "harvesting": busy,
    }


def _planner_next(account_id: str) -> str | None:
    return planner.next_run(account_id)


def _planner_harvest(account_id: str) -> str | None:
    return planner.next_harvest(account_id)


# ---------------- 元信息 / 健康 ----------------

@api.get("/health")
def health():
    return {"ok": True}


@api.get("/meta")
def meta():
    return {"version": __version__, "auth": bool(access_token()), "name": "Spark Cloud"}


# ---------------- 服务设置(网页修改端口) ----------------

def _locked_detail() -> str:
    """端口锁定场景的提示文案(Docker 容器 vs 系统环境变量)。"""
    if _in_docker():
        return ("当前为 Docker 部署,容器内端口已被固定(SPARK_PORT=8000),网页修改不会生效;"
                "请直接修改 docker-compose.yml(或飞牛「项目」配置)的 ports 映射(左侧数字),然后重新部署。")
    return ("检测到系统/服务环境变量已固定端口(SPARK_PORT),网页修改不会生效;"
            "请清除该环境变量后再启动服务。")


def _port_free(port: int) -> bool:
    """新端口是否可绑定(未被占用)。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _restart_service() -> None:
    """延迟 1.2s 后用全新进程重启服务,再立即退出当前进程。

    用 os._exit 终止(不触发 atexit),避免旧进程删除新进程写入的实例锁;
    新进程启动时会发现旧锁进程已死并自动接管。
    """
    import subprocess
    import sys
    import time
    time.sleep(1.2)
    script = str(BASE_DIR / "app.py")
    try:
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([sys.executable, script], cwd=str(BASE_DIR), creationflags=flags, close_fds=True)
        else:
            subprocess.Popen([sys.executable, script], cwd=str(BASE_DIR), start_new_session=True, close_fds=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("网页重启失败:%s", exc)
        os._exit(1)
    logger.info("服务已由网页触发重启")
    os._exit(0)


@api.get("/settings/port")
def settings_port_get():
    denied = _require_auth()
    if denied:
        return denied
    return {
        "port": web_port(),
        "saved_port": saved_web_port(),
        "locked": port_locked(),
        "docker": _in_docker(),
    }


@api.put("/settings/port")
def settings_port_put():
    denied = _require_auth()
    if denied:
        return denied
    if port_locked():
        return jsonify({"detail": _locked_detail()}), 400
    body = request.get_json(silent=True) or {}
    try:
        port = int(body.get("port", 0))
    except (TypeError, ValueError):
        return jsonify({"detail": "端口必须是数字"}), 400
    if not (1 <= port <= 65535):
        return jsonify({"detail": "端口范围需在 1~65535 之间"}), 400
    try:
        set_web_port(port)
    except Exception as exc:  # noqa: BLE001
        logger.error("写入端口失败:%s", exc)
        return jsonify({"detail": f"写入 .env 失败:{exc}"}), 500
    logger.info("网页已将监听端口修改为 %s(重启后生效)", port)
    return {"ok": True, "port": port, "saved_port": saved_web_port(), "needs_restart": True}


@api.post("/settings/restart")
def settings_restart():
    denied = _require_auth()
    if denied:
        return denied
    if port_locked():
        return jsonify({"detail": _locked_detail()}), 400
    target = saved_web_port()
    if not target:
        return jsonify({"detail": "尚未保存端口配置,请先修改端口"}), 400
    cur = web_port()
    if target != cur and not _port_free(target):
        return jsonify({"detail": f"新端口 {target} 已被其他程序占用,无法重启;请换一个端口"}), 400
    threading_start(_restart_service)
    return {"ok": True, "message": f"服务将在 2 秒后重启,请稍后用新地址访问(端口 {target})"}


# ---------------- 自定义背景图片 ----------------

BG_DIR = DATA / "bg"

_IMG_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "bmp")


def _bg_file() -> Path | None:
    """当前自定义背景文件(custom.*),不存在返回 None。"""
    if not BG_DIR.is_dir():
        return None
    for f in sorted(BG_DIR.glob("custom.*")):
        if f.is_file():
            return f
    return None


@api.get("/settings/bg")
def settings_bg_get():
    denied = _require_auth()
    if denied:
        return denied
    f = _bg_file()
    if f:
        return {"ok": True, "exists": True, "url": f"/bg/{f.name}"}
    return {"ok": True, "exists": False, "url": None}


@api.post("/settings/bg")
def settings_bg_upload():
    denied = _require_auth()
    if denied:
        return denied
    file = request.files.get("file")
    if not file:
        return jsonify({"detail": "缺少文件字段 file"}), 400
    fname = file.filename or ""
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in _IMG_EXTS:
        return jsonify({"detail": "仅支持图片文件(jpg/png/webp/gif/bmp)"}), 400
    raw = file.read()
    if len(raw) > 12 * 1024 * 1024:
        return jsonify({"detail": "图片过大(>12MB),请压缩后再上传"}), 400
    if not raw:
        return jsonify({"detail": "文件内容为空"}), 400
    # 简单魔数校验,防止上传非图片文件
    magic_ok = (
        raw.startswith(b"\xff\xd8")          # jpg
        or raw.startswith(b"\x89PNG")        # png
        or raw.startswith(b"GIF8")           # gif
        or raw.startswith(b"BM")             # bmp
        or raw.startswith(b"RIFF") and b"WEBP" in raw[:16]  # webp
    )
    if not magic_ok:
        return jsonify({"detail": "文件内容不是有效图片"}), 400
    BG_DIR.mkdir(parents=True, exist_ok=True)
    for old in BG_DIR.glob("custom.*"):
        old.unlink(missing_ok=True)
    ext = "jpg" if ext == "jpeg" else ext
    (BG_DIR / f"custom.{ext}").write_bytes(raw)
    logger.info("已更新自定义背景图片(%s, %s 字节)", ext, len(raw))
    return {"ok": True, "url": f"/bg/custom.{ext}"}


@api.delete("/settings/bg")
def settings_bg_clear():
    denied = _require_auth()
    if denied:
        return denied
    removed = 0
    if BG_DIR.is_dir():
        for old in BG_DIR.glob("custom.*"):
            old.unlink(missing_ok=True)
            removed += 1
    return {"ok": True, "removed": removed}


# ---------------- 表情包库 ----------------

_STICKER_MAX = 8 * 1024 * 1024  # 单张上限 8MB


def _sticker_magic_ok(raw: bytes) -> bool:
    return (
        raw.startswith(b"\xff\xd8")          # jpg
        or raw.startswith(b"\x89PNG")        # png
        or raw.startswith(b"GIF8")           # gif
        or raw.startswith(b"RIFF") and b"WEBP" in raw[:16]  # webp
    )


@api.get("/accounts/<account_id>/stickers")
def stickers_list(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    names = sticker_store.list_stickers(aid)
    return {"ok": True, "stickers": [{"name": n, "url": f"/stickers/{aid}/{n}"} for n in names]}


@api.post("/accounts/<account_id>/stickers")
def stickers_upload(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    files = request.files.getlist("file") or ([request.files.get("file")] if request.files.get("file") else [])
    if not files or not files[0]:
        return jsonify({"detail": "缺少文件字段 file"}), 400
    saved, skipped = [], []
    for f in files[:20]:  # 单次最多 20 张
        fname = f.filename or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in sticker_store.STICKER_EXTS:
            skipped.append({"name": fname, "reason": "仅支持 jpg/png/webp/gif"})
            continue
        raw = f.read()
        if not raw or len(raw) > _STICKER_MAX:
            skipped.append({"name": fname, "reason": "为空或超过 8MB"})
            continue
        if not _sticker_magic_ok(raw):
            skipped.append({"name": fname, "reason": "不是有效图片"})
            continue
        saved.append(sticker_store.save_sticker(aid, fname, raw))
    logger.info("[%s] 上传表情包 %s 张(跳过 %s)", aid, len(saved), len(skipped))
    return {"ok": True, "saved": saved, "skipped": skipped}


@api.delete("/accounts/<account_id>/stickers/<name>")
def stickers_delete(account_id: str, name: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    if not sticker_store.delete_sticker(aid, name):
        return jsonify({"detail": "文件不存在或路径非法"}), 404
    return {"ok": True}


# ---------------- 发送历史 / 统计(功能1) ----------------

@api.get("/accounts/<account_id>/history")
def history_list(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    return {"ok": True, "records": history_store.recent(aid, limit)}


@api.get("/accounts/<account_id>/stats")
def history_stats(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return {"ok": True, "stats": history_store.stats(aid)}


# ---------------- 通知推送(功能2) ----------------

@api.get("/notify")
def notify_get():
    denied = _require_auth()
    if denied:
        return denied
    return {"ok": True, "notify": notify_store.load()}


@api.put("/notify")
@api.post("/notify")
def notify_put():
    denied = _require_auth()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    return {"ok": True, "notify": notify_store.save(body)}


@api.post("/notify/test")
def notify_test():
    denied = _require_auth()
    if denied:
        return denied
    return {"ok": True, "result": notify_store.test()}


# ---------------- 微信直连(扫码绑定 + 推送) ----------------

def _wx():
    from .settings import data_dir
    from .wxbot import init_wxbot
    return init_wxbot(data_dir())


@api.post("/wx/login")
def wx_login():
    denied = _require_auth()
    if denied:
        return denied
    _wx().start_login()
    return {"ok": True}


@api.get("/wx/status")
def wx_status():
    denied = _require_auth()
    if denied:
        return denied
    return {"ok": True, "wx": _wx().status()}


@api.post("/wx/verify")
def wx_verify():
    denied = _require_auth()
    if denied:
        return denied
    code = str((request.get_json(silent=True) or {}).get("code") or "")
    return {"ok": _wx().submit_verify(code)}


@api.post("/wx/logout")
def wx_logout():
    denied = _require_auth()
    if denied:
        return denied
    return {"ok": _wx().logout()}


@api.post("/wx/test")
def wx_test():
    denied = _require_auth()
    if denied:
        return denied
    ok, detail = _wx().send_wx("Spark Cloud 测试通知:收到即绑定成功 ✅")
    return {"ok": ok, "detail": detail}


# ---------------- 账号管理 ----------------

@api.get("/accounts")
def accounts():
    denied = _require_auth()
    if denied:
        return denied
    from .browser import slots_available
    from .browser import MAX_BROWSERS
    accts = [_account_summary(a) for a in acc_store.list_accounts()]
    return {
        "accounts": accts,
        "current": DEFAULT_ACCOUNT,
        "max_concurrent": MAX_BROWSERS,
        "browser_slots_available": slots_available(),
        "version": __version__,
    }


@api.post("/accounts")
def account_create():
    denied = _require_auth()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    acc = acc_store.create(name=str(body.get("name", "")), note=str(body.get("note", "")))
    _apply_plan(acc["id"])
    logger.info("已创建账号:%s(%s)", acc["name"], acc["id"])
    return {"ok": True, "account": _account_summary(acc)}


@api.patch("/accounts/<account_id>")
def account_update(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    acc = acc_store.update(
        aid,
        name=body.get("name"),
        note=body.get("note"),
        enabled=body.get("enabled"),
    )
    if acc is None:
        return jsonify({"detail": "默认账号不允许停用/删除"}), 400
    _apply_plan(aid)
    return {"ok": True, "account": _account_summary(acc)}


@api.delete("/accounts/<account_id>")
def account_delete(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    if aid == DEFAULT_ACCOUNT:
        return jsonify({"detail": "默认账号不允许删除"}), 400
    if runner.is_busy(aid):
        return jsonify({"detail": "该账号正在执行任务,请稍后再试"}), 409
    qrlogin.cancel(aid)
    _forget_plan(aid)
    acc_store.remove(aid)
    logger.info("已删除账号:%s", aid)
    return {"ok": True}


def _apply_plan(account_id: str) -> None:
    planner.apply(account_id)


def _forget_plan(account_id: str) -> None:
    planner.forget(account_id)


# ---------------- 状态 / 配置 ----------------

@api.get("/accounts/<account_id>/status")
def account_status(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    r = rt.load(aid)
    state_file = account_dir(aid) / "state.json"
    return {
        "state_file_exists": state_file.exists(),
        "state_file_path": str(state_file) if state_file.exists() else None,
        "session_status": r.get("session_status", "unknown"),
        "running": r.get("running", False),
        "last_run": r.get("last_run"),
        "next_run": _planner_next(aid),
        "next_harvest": _planner_harvest(aid),
        "history_count": 0,
        "auth_required": bool(access_token()),
        "account_id": aid,
        "version": __version__,
    }


@api.get("/accounts/<account_id>/config")
def account_config(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return acc_store.load_config(aid)


@api.put("/accounts/<account_id>/config")
@api.post("/accounts/<account_id>/config")
def account_config_save(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    patch = body.get("config") if isinstance(body.get("config"), dict) else body
    try:
        cfg = acc_store.save_config(aid, patch)
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    _apply_plan(aid)
    return {"ok": True, "config": cfg}


# ---------------- 好友台账 ----------------

def _contact_view(e: dict) -> dict:
    name = e.get("name", "")
    return {
        "display_name": name,
        "nickname": e.get("nickname", ""),
        "account": e.get("account", ""),
        "avatar": e.get("avatar", ""),
        "streak_days": e.get("days", 0),
        "spark_days": e.get("days", 0),
        "selected": bool(e.get("selected")),
        "last_status": "success" if e.get("last_sent") else "pending",
        "last_sent_at": e.get("last_sent"),
    }


@api.get("/accounts/<account_id>/friends")
def account_friends(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    entries = book.load(aid)
    r = rt.load(aid)
    pending = runner.pending_targets(aid)
    return {
        "entries": entries,
        "contacts": [_contact_view(e) for e in entries],
        "selected_count": sum(1 for e in entries if e.get("selected")),
        "pending_send": [{"display_name": p["name"], "send_channel": p.get("channel", "consumer")} for p in pending],
        "contacts_at": r.get("contacts_at"),
        "contacts_error": r.get("contacts_error"),
        "fetching": runner.is_busy(aid),
        "harvesting": runner.is_busy(aid),
        "harvest_last": r.get("harvest_last"),
        "b_channel_daily": r.get("b_channel", {}),
        "account_id": aid,
    }


@api.put("/accounts/<account_id>/friends")
def account_friends_save(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    changes = []
    for item in body.get("entries") or []:
        name = str(item.get("display_name", "")).strip()
        if name and isinstance(item.get("selected"), bool):
            changes.append({
                "name": name,
                "selected": item["selected"],
                "order": item.get("selected_order"),
            })
    stats = book.set_selection(aid, changes)
    return {"ok": True, **stats}


@api.post("/accounts/<account_id>/friends/remove")
def account_friends_remove(account_id: str):
    """移除好友(从台账中隐藏;不影响抖音好友关系,同步也不会再出现)。"""
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    names = [str(n).strip() for n in (body.get("names") or []) if str(n).strip()]
    if not names:
        return jsonify({"detail": "缺少 names 字段"}), 400
    if runner.is_busy(aid):
        return jsonify({"detail": "该账号正在执行任务,请稍后再试"}), 409
    stats = book.remove_names(aid, names)
    logger.info("[%s] 已移除台账好友 %s 个:%s", aid, stats["removed"], ", ".join(names[:10]))
    return {"ok": True, **stats}


@api.get("/accounts/<account_id>/report")
def account_report(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return book.stats(aid)


# ---------------- 任务 ----------------

@api.post("/accounts/<account_id>/sync")
def account_sync(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    if runner.is_busy(aid):
        return jsonify({"detail": "该账号已有任务在运行"}), 409
    threading_start(lambda: runner.sync_contacts(aid))
    return {"ok": True, "started": True}


@api.post("/accounts/<account_id>/harvest")
def account_harvest(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    if runner.is_busy(aid):
        return jsonify({"detail": "该账号已有任务在运行"}), 409
    threading_start(lambda: runner.run_scan(aid))
    return {"ok": True, "started": True}


@api.post("/accounts/<account_id>/run")
def account_run(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    dry = bool(body.get("dry"))
    if not book.selected(aid) and not body.get("force"):
        return jsonify({"detail": "未勾选任何好友!请先在「好友」页勾选后再执行。"}), 400
    if runner.is_busy(aid):
        return jsonify({"detail": "该账号已有任务在运行"}), 409
    threading_start(lambda: runner.run_once(aid, dry=dry))
    return {"ok": True, "started": True}


@api.post("/accounts/<account_id>/stop")
def account_stop(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, _ = _resolve(account_id)
    runner.request_stop(aid)
    runner.reset(aid)
    logger.info("[%s] 已强制重置运行状态", aid)
    return {"ok": True, "message": "运行状态已强制重置"}


@api.post("/stop-all")
def stop_all():
    denied = _require_auth()
    if denied:
        return denied
    runner.request_stop_all()
    runner.reset_all()
    return {"ok": True, "message": "全部账号运行状态已重置"}


def threading_start(fn) -> None:
    import threading
    threading.Thread(target=fn, daemon=True).start()


# ---------------- 登录凭证 / 扫码 ----------------

@api.post("/accounts/<account_id>/credential")
def credential_upload(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    file = request.files.get("file")
    if not file:
        return jsonify({"detail": "缺少文件字段 file"}), 400
    raw = file.read()
    if len(raw) > 5 * 1024 * 1024:
        return jsonify({"detail": "文件过大"}), 400
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return jsonify({"detail": "不是合法的 JSON 文件"}), 400
    if not isinstance(data.get("cookies"), list) or not data["cookies"]:
        return jsonify({"detail": "缺少 cookies 字段,请确认是 Playwright 导出的登录态文件"}), 400
    d = account_dir(aid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_bytes(raw)
    rt.save(aid, session_status="uploaded")
    logger.info("[%s] 已更新登录态 state.json(%s 字节)", aid, len(raw))
    return {"ok": True, "size": len(raw)}


@api.post("/accounts/<account_id>/qr")
def qr_start(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return qrlogin.start(aid)


@api.get("/accounts/<account_id>/qr")
def qr_poll(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return qrlogin.poll(aid)


@api.delete("/accounts/<account_id>/qr")
def qr_cancel(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, err = _resolve(account_id)
    if err:
        return err
    return qrlogin.cancel(aid)


# ---------------- 微信推送专用二维码页(令牌自鉴权,免网页登录) ----------------

_QRPUB_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>抖音登录二维码</title>
<style>
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#101418;color:#e8eaed;
display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;text-align:center}
#box{background:#fff;padding:16px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.5)}
#qr{width:min(78vw,320px);height:min(78vw,320px)}
#ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#999;font-size:14px}
#st{margin-top:18px;font-size:15px;line-height:1.7;max-width:86vw;white-space:pre-line}
.ok{color:#34c759}.warn{color:#ffd60a}.err{color:#ff6b6b}
img{width:100%;height:100%;display:block}
</style></head><body>
<div id="box"><div id="qr"><div id="ph">加载中…</div></div></div>
<div id="st">正在连接…</div>
<script>
const AID="__AID__",T="__T__",qr=document.getElementById("qr"),st=document.getElementById("st");
let last="",timer=setInterval(poll,2000);
function setQr(svg){if(svg&&svg!==last){last=svg;qr.innerHTML='<img src="'+svg+'">';}}
function done(msg,cls){st.innerHTML='<span class="'+cls+'">'+msg+'</span>';clearInterval(timer);}
async function poll(){
 try{
  const r=await fetch("data/"+AID+"?t="+T,{cache:"no-store"});
  if(r.status===403)return done("链接已失效<br>请回微信重新发送「登录」","err");
  const d=await r.json();
  if(d.status==="waiting"){
    if(d.svg)setQr(d.svg);
    if(d.message&&d.message.indexOf("验证")>=0)
      st.innerHTML="⚠ 触发安全验证,页面已更新为验证码<br>请重新截图并用抖音识别";
    else
      st.innerHTML="二维码已就绪,请打开抖音<br>「扫一扫 → 相册」选中本页截图识别";
  }else if(d.status==="preparing"){st.textContent=d.message||"正在启动扫码环境…";}
  else if(d.status==="done"){done("✅ 登录成功,可以关闭本页","ok");}
  else if(d.status==="expired"){done("二维码已过期<br>请回微信重新发送「登录」","err");}
  else if(d.status==="failed"){done("登录失败:"+(d.error||d.message||"未知")+"<br>可回微信重新发送「登录」","err");}
  else if(d.status==="canceled"){done("登录已取消","warn");}
  else{done("会话已结束<br>请回微信重新发送「登录」","err");}
 }catch(e){st.textContent="网络异常,重试中…";}
}
poll();
</script></body></html>"""


@api.get("/qrpub/data/<account_id>")
def qrpub_data(account_id: str):
    """二维码页轮询数据:令牌匹配才返回(SVG 由后端渲染,前端零依赖)。"""
    tok = qrlogin.qr_token(account_id)
    if not tok or request.args.get("t", "") != tok:
        return jsonify({"detail": "链接已失效,请在微信重新发送「登录」"}), 403
    st = qrlogin.poll(account_id) or {}
    svg = ""
    if st.get("qrcode"):
        from .wxbot import _qr_svg
        svg = _qr_svg(st["qrcode"])
    return {"status": st.get("status"), "message": st.get("message"),
            "svg": svg, "error": st.get("error")}


@api.get("/qrpub/<account_id>")
def qrpub_page(account_id: str):
    import re as _re
    if not _re.fullmatch(r"[\w.-]{1,64}", account_id or ""):
        return jsonify({"detail": "账号不存在"}), 404
    tok = qrlogin.qr_token(account_id)
    if not tok or request.args.get("t", "") != tok:
        return Response("链接已失效,请在微信重新发送「登录」",
                        mimetype="text/plain; charset=utf-8"), 403
    html = _QRPUB_HTML.replace("__AID__", account_id).replace("__T__", tok)
    return Response(html, mimetype="text/html; charset=utf-8")


# ---------------- 日志 ----------------

@api.get("/accounts/<account_id>/logs")
def account_logs(account_id: str):
    denied = _require_auth()
    if denied:
        return denied
    aid, _ = _resolve(account_id)
    try:
        n = max(10, min(int(request.args.get("n", 300)), 1000))
    except ValueError:
        n = 300
    return {"logs": "\n".join(logstore.recent(n))}


@api.after_request
def api_no_cache(response):
    """所有 API 响应禁用缓存,避免浏览器缓存 GET 结果导致数据不刷新。"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


# 头像静态文件由 app.py 挂载到 /avatars/<path:filename>
