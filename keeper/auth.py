"""Web 管理后台登录账号系统。

- 账号(用户名+密码)存 data/web_account.json,密码用 PBKDF2 加盐哈希,不存明文;
- 未设置账号(文件不存在) = 登录未启用,网页直接可用(保持现状);
- 登录成功后签发内存会话 token(进程内有效,重启需重新登录);
- 与现有 SPARK_TOKEN(X-Token) 鉴权叠加:配置了令牌时两者都要过。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time

from .settings import DATA

ACCOUNT_FILE = DATA / "web_account.json"
SESSION_TTL = 7 * 24 * 3600  # 会话有效期 7 天

# 内存会话表: token -> 过期时间戳(秒)
SESSIONS: dict[str, float] = {}


def _load() -> dict | None:
    try:
        return json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 120_000
    ).hex()


def enabled() -> bool:
    """登录是否启用(设置过账号且未关闭)。"""
    a = _load()
    return bool(a and a.get("enabled"))


def username() -> str:
    a = _load()
    return str((a or {}).get("username", "")) if enabled() else ""


def verify(user: str, password: str) -> bool:
    a = _load()
    if not a:
        return False
    ok_user = hmac.compare_digest(str(a.get("username", "")), user)
    ok_pw = hmac.compare_digest(str(a.get("hash", "")), _hash(password, str(a["salt"])))
    return ok_user and ok_pw


def setup(user: str, password: str, enable: bool = True) -> None:
    """创建/更新账号(enable=False 时关闭登录但保留账号信息)。"""
    salt = secrets.token_hex(16)
    data = {"username": user, "salt": salt, "hash": _hash(password, salt), "enabled": enable}
    DATA.mkdir(parents=True, exist_ok=True)
    ACCOUNT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def disable() -> None:
    a = _load()
    if a:
        a["enabled"] = False
        ACCOUNT_FILE.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")


def create_session() -> str:
    token = secrets.token_hex(24)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token


def check_session(token: str) -> bool:
    exp = SESSIONS.get(token)
    if not exp:
        return False
    if time.time() > exp:
        SESSIONS.pop(token, None)
        return False
    return True


def destroy_session(token: str) -> None:
    SESSIONS.pop(token, None)
