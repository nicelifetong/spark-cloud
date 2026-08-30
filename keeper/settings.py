"""全局设置:环境变量、目录布局、访问令牌与默认配置。

配置优先级:环境变量 > 本地 .env 文件 > 代码默认值。
所有运行数据位于 data/ 下,结构:
    data/token                       自动生成的访问令牌(未通过环境变量指定时)
    data/accounts.json               账号注册表
    data/accounts/<id>/account.json  账号元信息
    data/accounts/<id>/config.json   该账号配置
    data/accounts/<id>/state.json    抖音登录态(Playwright storage_state)
    data/accounts/<id>/ledger.json   好友台账
    data/accounts/<id>/runtime.json  运行状态(上次运行/下次运行/会话状态)
    data/avatars/<id>/               头像缓存
"""
from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path

# ---------- 路径 ----------
BASE_DIR = Path(__file__).resolve().parent.parent

def data_dir() -> Path:
    """数据根目录:优先环境变量 SPARK_DATA,否则项目内 data/。"""
    override = os.environ.get("SPARK_DATA", "").strip()
    return Path(override) if override else (BASE_DIR / "data")

DATA = data_dir()
ACCOUNTS_ROOT = DATA / "accounts"
AVATAR_ROOT = DATA / "avatars"
TOKEN_FILE = DATA / "token"
LOCK_FILE = DATA / "run.pid"

def account_dir(account_id: str) -> Path:
    return ACCOUNTS_ROOT / account_id

# ---------- 环境变量 ----------
# 记录 .env 加载前已存在的环境变量(系统/Docker compose 注入),
# 用于判断某个配置是否被部署环境"固定"(此时网页修改无效)。
_PRELOAD_ENV: set = set(os.environ.keys())

def _load_dotenv() -> None:
    """读取项目根目录 .env(不覆盖已有环境变量)。"""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "TZ":
            # Windows 下 Python 的 time 模块遇到 TZ 环境变量会用 CRT 解析,
            # "Asia/Shanghai" 这类 POSIX 时区名无法识别,会导致本地时区退化为 UTC,
            # 使所有 datetime.now().astimezone() 时间错 8 小时(定时/台账/日志)。
            # Docker 场景的 TZ 由 compose environment 注入,不经过这里,不受影响。
            continue
        os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

def web_port() -> int:
    try:
        return int(os.environ.get("SPARK_PORT", os.environ.get("PORT", "8000")))
    except ValueError:
        return 8000

def web_host() -> str:
    return os.environ.get("SPARK_HOST", os.environ.get("HOST", "0.0.0.0"))

# ---------- 端口持久化(网页修改端口) ----------
ENV_FILE = BASE_DIR / ".env"

def _in_docker() -> bool:
    """是否运行在 Docker 容器内。"""
    try:
        if Path("/.dockerenv").exists():
            return True
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists() and "docker" in cgroup.read_text(errors="ignore"):
            return True
    except Exception:
        pass
    return False

def port_locked() -> bool:
    """端口是否由部署环境固定(此时网页改 .env 不会生效)。

    - Docker compose 通过 environment 注入 SPARK_PORT=8000 → 固定;
    - Linux 服务器由 systemd / docker run -e 注入 SPARK_PORT → 固定;
    - Windows 本地用 bat 启动:脚本只读取 .env 用于显示,不注入 SPARK_PORT
      (已改用独立变量名),不算固定,网页可正常修改端口。
    """
    if "SPARK_PORT" not in _PRELOAD_ENV:
        return False
    return _in_docker() or os.name != "nt"

def saved_web_port() -> int | None:
    """.env 中显式保存的 SPARK_PORT(未配置返回 None)。"""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        if key.strip() == "SPARK_PORT":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None

def set_web_port(port: int) -> int:
    """把 SPARK_PORT 写入/更新 .env(网页修改端口;重启后生效)。"""
    port = int(port)
    if not (1 <= port <= 65535):
        raise ValueError("端口范围需在 1~65535 之间")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out: list[str] = []
    found = False
    for line in lines:
        s = line.strip()
        if (s.startswith("SPARK_PORT=") or s.startswith("SPARK_PORT =")) and not s.startswith("#"):
            out.append(f"SPARK_PORT={port}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"SPARK_PORT={port}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    return port

def session_timezone() -> str:
    return os.environ.get("TZ", "Asia/Shanghai")

_token_lock = threading.Lock()

def access_token() -> str:
    """访问令牌:SPARK_TOKEN > data/token(自动生成) > 空。

    返回 "" 表示未启用鉴权。
    """
    env_token = os.environ.get("SPARK_TOKEN", os.environ.get("AUTH_TOKEN", "")).strip()
    if env_token:
        return env_token
    with _token_lock:
        DATA.mkdir(parents=True, exist_ok=True)
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text(encoding="utf-8").strip() or ""
        token = secrets.token_hex(16)
        TOKEN_FILE.write_text(token, encoding="utf-8")
        return token

def reset_token() -> str:
    """重新生成访问令牌,返回新值。"""
    with _token_lock:
        DATA.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        TOKEN_FILE.write_text(token, encoding="utf-8")
        return token

# ---------- 默认账号 ----------
DEFAULT_ACCOUNT = "default"

# ---------- 每账号配置默认值 ----------
DEFAULT_CONFIG: dict = {
    "schedule_time": "21:00",       # 每日发送时间 HH:MM(服务器时区)
    "jitter_minutes": 30,           # 随机浮动窗口:实际在 [time, time+jitter] 内随机
    "gap_min": 6,                   # 相邻好友最小间隔(秒)
    "gap_max": 12,                  # 相邻好友最大间隔(秒)
    "max_per_run": 0,               # 单次最多发送人数(0 = 不限制)
    "messages": ["🔥 续火花", "今天也要开心哦 🔥", "晚上好 🔥"],
    "themes": [],                   # 勾选的内置主题文案 id(见 keeper/messages.py THEMES)
    "sticker_enabled": False,       # 发送表情包(图片/GIF)总开关
    "sticker_chance": 30,           # 每个好友触发表情包的概率(%)
    "auto_enabled": True,           # 自动运行总开关
    "allow_first": False,           # 允许给无会话好友发首条消息(高风险)
    "first_limit": 1,               # 首条消息单日上限
    "harvest_day": "mon",           # 周级好友抖音号扫描(mon/tue/.../sun/off)
    "max_scrolls": 80,              # 单次扫描最大滚动轮数
    "scan_interval": 0.5,           # 扫描滚动间隔(秒)
    "friend_overrides": {},         # 按好友差异:{名字: {skip, pool[], sticker_chance|null}}
}
