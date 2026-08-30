"""事件通知推送:data/notify.json(全局一份,不分账号)。

渠道:
- clawbot / OpenClaw 网关:POST {url},JSON {"channel","to","text"},可选 X-API-Token;
  兼容 openclaw-weixin / OpenClaw-Wechat 等微信接入插件与任何接受该结构的机器人网关;
- bark:GET https://api.day.app/<key>/<title>/<text>(url 填 key;填完整 http(s) 地址则按模板替换 {title}/{text});
- serverchan(Server酱):GET https://sctapi.ftqq.com/<key>.send?title=&desp=;
- webhook:POST {url},JSON {"title","text"}。

send() 永不抛异常——通知失败只记日志,绝不影响发送主流程。
"""
from __future__ import annotations

import json
import logging
from urllib.parse import quote

import requests

from .storage import read_json, write_json

logger = logging.getLogger("spark")

CHANNELS = ("clawbot", "wx_direct", "bark", "serverchan", "webhook")

_DEFAULT: dict = {
    "enabled": False,
    "channel": "clawbot",
    "url": "",          # clawbot=网关地址; bark=key 或完整模板; serverchan=SendKey; webhook=地址
    "token": "",        # clawbot 网关令牌(可选); 其余渠道忽略
    "to": "",           # clawbot 接收目标(微信联系人/群 id,可选)
    "events": {
        "send_fail": True,       # 有好友发送失败
        "send_ok": True,         # 本轮成功名单(实时)
        "login_expired": True,   # 登录态失效
        "rate_limited": True,    # 触发抖音限流
    },
}


def _path():
    from .settings import data_dir
    return data_dir() / "notify.json"


def load() -> dict:
    cfg = dict(_DEFAULT)
    data = read_json(_path(), {})
    if isinstance(data, dict):
        cfg.update({k: v for k, v in data.items() if k in cfg})
        ev = dict(_DEFAULT["events"])
        if isinstance(data.get("events"), dict):
            ev.update({k: bool(v) for k, v in data["events"].items() if k in ev})
        cfg["events"] = ev
    return cfg


def save(patch: dict | None = None) -> dict:
    cfg = load()
    if patch:
        for k, v in patch.items():
            if k == "events" and isinstance(v, dict):
                cfg["events"].update({k2: bool(v2) for k2, v2 in v.items() if k2 in cfg["events"]})
            elif k in cfg and k != "events":
                cfg[k] = v
    cfg["channel"] = cfg["channel"] if cfg["channel"] in CHANNELS else "clawbot"
    cfg["enabled"] = bool(cfg["enabled"])
    write_json(_path(), cfg)
    return cfg


def send(title: str, text: str, event: str | None = None) -> dict:
    """推送一条通知。event 为事件名,用于开关过滤;None 表示始终发送(测试)。"""
    cfg = load()
    if not cfg.get("enabled"):
        return {"ok": False, "skipped": "通知未开启"}
    if event and not cfg.get("events", {}).get(event, True):
        return {"ok": False, "skipped": f"事件 {event} 未勾选"}
    channel = cfg.get("channel", "clawbot")
    url = str(cfg.get("url") or "").strip()
    if channel != "wx_direct" and not url:
        return {"ok": False, "skipped": "未配置推送地址"}  # wx_direct 直连,无需 URL
    channel = cfg.get("channel", "clawbot")
    token = str(cfg.get("token") or "").strip()
    to = str(cfg.get("to") or "").strip()
    try:
        if channel == "wx_direct":
            from .settings import data_dir
            from .wxbot import init_wxbot
            ok, detail = init_wxbot(data_dir()).send_wx(f"{title}\n{text}")
            logger.info("[notify] wx_direct 推送%s(%s)", "成功" if ok else f"失败: {detail}", event or "test")
            return {"ok": ok, "error": None if ok else detail}
        if channel == "clawbot":
            payload = {"channel": "wechat", "to": to, "title": title,
                       "text": f"{title}\n{text}", "message": f"{title}\n{text}"}
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-API-Token"] = token
                headers["Authorization"] = f"Bearer {token}"
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        elif channel == "bark":
            if url.startswith("http"):
                target = url.replace("{title}", quote(title)).replace("{text}", quote(text))
                resp = requests.get(target, timeout=10)
            else:
                resp = requests.get(
                    f"https://api.day.app/{url}/{quote(title)}/{quote(text)}", timeout=10)
        elif channel == "serverchan":
            resp = requests.get(
                f"https://sctapi.ftqq.com/{url}.send",
                params={"title": title, "desp": text}, timeout=10)
        else:  # webhook
            resp = requests.post(url, json={"title": title, "text": text}, timeout=10)
        ok = 200 <= resp.status_code < 300
        logger.info("[notify] %s 推送%s(%s)", channel, "成功" if ok else f"失败 HTTP {resp.status_code}", event or "test")
        return {"ok": ok, "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[notify] 推送异常(%s): %s", channel, exc)
        return {"ok": False, "error": str(exc)}


def test() -> dict:
    return send("Spark Cloud 测试通知", "这是一条测试推送,收到说明通知通道配置正确 ✅")
