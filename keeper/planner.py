"""轻量定时调度器:不依赖任何第三方调度库。

每个账号维护一个「下次运行时间」,调度线程睡到最早到期的账号并触发发送;
触发后在后台线程里执行,同时把该账号重排到明天(带随机浮动,模拟真人节奏)。
周级扫描(好友抖音号)同理,单独维护一个时间表。
"""
from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timedelta, timezone

from . import accounts as acc_store
from .settings import DEFAULT_CONFIG

logger = logging.getLogger("spark")

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
MAX_SLEEP = 30  # 循环唤醒上限(秒)

# 中国无夏令时,固定 UTC+8,与 Playwright 浏览器时区(Asia/Shanghai)保持一致。
# 不依赖进程/系统时区:Windows 上 TZ 环境变量可能导致 Python 把本地时区误判为 UTC,
# 从而把 21:00 当成 UTC 21 点,换算成本地时间就错 8 小时。
CN_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def _now() -> datetime:
    """当前北京时间(带 +08:00 时区)。"""
    return datetime.now(CN_TZ)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = str(value).split(":")
    return int(hh), int(mm)


def _next_daily(base_time: str, jitter_min: int, now: datetime | None = None) -> datetime:
    """按「今天 base 时间 + 随机浮动(0..jitter)」计算下一次;已过则顺延到明天。"""
    now = now or _now()
    hh, mm = _parse_hhmm(base_time)
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if jitter_min > 0:
        candidate = candidate + timedelta(minutes=random.uniform(0, jitter_min))
    if candidate <= now:
        tomorrow = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        candidate = tomorrow + (timedelta(minutes=random.uniform(0, jitter_min)) if jitter_min > 0 else timedelta(0))
    return candidate


def _next_weekly(weekday: int, now: datetime | None = None) -> datetime:
    """下一个指定星期几的 03:00。"""
    now = now or _now()
    days_ahead = (weekday - now.weekday()) % 7
    target = (now + timedelta(days=days_ahead)).replace(hour=3, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=7)
    return target


class Planner(threading.Thread):
    """调度线程。attach() 提供触发回调,apply() 根据账号配置注册/更新计划。"""

    def __init__(self):
        super().__init__(daemon=True, name="spark-planner")
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._runs: dict[str, datetime] = {}     # account_id -> 下次发送
        self._harvests: dict[str, datetime] = {} # account_id -> 下次扫描
        self._on_run = None
        self._on_harvest = None

    # ---- 回调注册 ----
    def attach(self, on_run, on_harvest) -> None:
        self._on_run = on_run
        self._on_harvest = on_harvest

    # ---- 计划管理 ----
    def apply(self, account_id: str) -> None:
        """根据账号启用状态与配置重算计划。"""
        with self._lock:
            meta = acc_store.get_account(account_id)
            cfg = acc_store.load_config(account_id)
            enabled = bool(meta and meta.get("enabled", True)) and bool(cfg.get("auto_enabled", True))
            if not enabled:
                self._runs.pop(account_id, None)
            else:
                self._runs[account_id] = _next_daily(cfg["schedule_time"], cfg["jitter_minutes"])
            day = str(cfg.get("harvest_day") or "off").lower()
            if day in WEEKDAYS:
                self._harvests[account_id] = _next_weekly(WEEKDAYS[day])
            else:
                self._harvests.pop(account_id, None)
            logger.info("[%s] 计划已更新:发送 %s,扫描 %s",
                        account_id,
                        self._runs.get(account_id).strftime("%m-%d %H:%M") if account_id in self._runs else "关闭",
                        self._harvests.get(account_id).strftime("%m-%d %H:%M") if account_id in self._harvests else "关闭")
        self._wake.set()

    def apply_all(self) -> None:
        for acc in acc_store.list_accounts():
            self.apply(acc["id"])

    def forget(self, account_id: str) -> None:
        with self._lock:
            self._runs.pop(account_id, None)
            self._harvests.pop(account_id, None)
        self._wake.set()

    def next_run(self, account_id: str) -> str | None:
        with self._lock:
            t = self._runs.get(account_id)
            return t.isoformat() if t else None

    def next_harvest(self, account_id: str) -> str | None:
        with self._lock:
            t = self._harvests.get(account_id)
            return t.isoformat() if t else None

    # ---- 调度主循环 ----
    def run(self) -> None:
        logger.info("调度线程已启动")
        while not self._stop.is_set():
            now = _now()
            due_runs: list[str] = []
            due_harvests: list[str] = []
            with self._lock:
                due_runs = [aid for aid, t in self._runs.items() if t <= now]
                due_harvests = [aid for aid, t in self._harvests.items() if t <= now]
                for aid in due_runs:
                    self._runs[aid] = _next_daily(
                        acc_store.load_config(aid)["schedule_time"],
                        acc_store.load_config(aid)["jitter_minutes"],
                    )
                for aid in due_harvests:
                    day = str(acc_store.load_config(aid).get("harvest_day") or "off").lower()
                    self._harvests[aid] = _next_weekly(WEEKDAYS[day]) if day in WEEKDAYS else _next_weekly(WEEKDAYS[day])

            for aid in due_runs:
                logger.info("[%s] 定时任务触发", aid)
                if self._on_run:
                    threading.Thread(target=self._on_run, args=(aid,), daemon=True).start()
            for aid in due_harvests:
                logger.info("[%s] 周级扫描触发", aid)
                if self._on_harvest:
                    threading.Thread(target=self._on_harvest, args=(aid,), daemon=True).start()

            with self._lock:
                wait = min([t for t in self._runs.values()] + [t for t in self._harvests.values()] or [])
                seconds = max(0.5, min((wait - now).total_seconds(), MAX_SLEEP)) if wait else MAX_SLEEP
            self._wake.wait(timeout=seconds)
            self._wake.clear()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()


# ---------------- 模块级单例 ----------------
_planner: Planner | None = None
_planner_guard = threading.Lock()


def get() -> Planner:
    """获取全局调度器实例(懒创建)。"""
    global _planner
    with _planner_guard:
        if _planner is None:
            _planner = Planner()
        return _planner


def attach(on_run, on_harvest) -> None:
    get().attach(on_run, on_harvest)


def apply(account_id: str) -> None:
    get().apply(account_id)


def apply_all() -> None:
    get().apply_all()


def forget(account_id: str) -> None:
    get().forget(account_id)


def next_run(account_id: str) -> str | None:
    return get().next_run(account_id)


def next_harvest(account_id: str) -> str | None:
    return get().next_harvest(account_id)


def start() -> None:
    get().start()


def shutdown() -> None:
    get().shutdown()
