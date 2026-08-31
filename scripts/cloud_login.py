# -*- coding: utf-8 -*-
"""云端扫码登录:在 GitHub Actions 里跑,登录二维码推送到企业微信群,
用户用抖音 App 扫群里的码,登录态自动写入 data/ 供 seal 回传。

前置:data/notify.json 里已配置 wecom 渠道(Termux 后台设置后 sync.sh 上传)。
"""
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keeper import qrlogin  # noqa: E402
from keeper.settings import DEFAULT_ACCOUNT  # noqa: E402


def _wecom_url() -> str:
    p = ROOT / "data" / "notify.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    url = str(cfg.get("url") or "").strip()
    if str(cfg.get("channel")) == "wecom" and url.startswith("http"):
        return url
    return ""


def _push_image(url: str, dataurl: str) -> None:
    png = base64.b64decode(dataurl.split(",", 1)[1])
    requests.post(url, json={"msgtype": "image", "image": {
        "base64": base64.b64encode(png).decode(),
        "md5": hashlib.md5(png).hexdigest(),
    }}, timeout=15)


def _push_text(url: str, text: str) -> None:
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=15)
    except Exception:
        pass


def main() -> None:
    url = _wecom_url()
    if not url:
        sys.exit("[x] data/notify.json 未配置企业微信(wecom)Webhook;先在后台配置好并 sync.sh 上传,再跑本 workflow")
    aid = DEFAULT_ACCOUNT
    qrlogin.start(aid)
    last_qr, pushed, restarts = "", 0, 0
    deadline = time.time() + 420
    while time.time() < deadline:
        st = qrlogin.poll(aid) or {}
        qr, status = st.get("qrcode") or "", st.get("status")
        if qr and qr != last_qr:
            last_qr = qr
            pushed += 1
            try:
                _push_image(url, qr)
                _push_text(url, f"【spark-cloud】第 {pushed} 张登录二维码:请用抖音 App 扫码(约 1 分钟内有效)")
            except Exception as exc:  # 推送失败不中断,继续轮询
                print(f"[!] 推送失败: {exc}")
            print(f"[i] 已推送第 {pushed} 张二维码 (status={status})")
        if status == "done":
            _push_text(url, "【spark-cloud】扫码登录成功,登录态已写入云端 ✓")
            print("[✓] 登录成功")
            return
        if status in ("expired", "failed"):
            if restarts >= 2:
                _push_text(url, f"【spark-cloud】扫码失败:{st.get('message')},请重新运行 workflow")
                sys.exit(f"[x] {st.get('message')}")
            restarts += 1
            print(f"[i] 会话 {status},重新发起(第 {restarts} 次)")
            last_qr = ""
            qrlogin.start(aid)
        time.sleep(3)
    _push_text(url, "【spark-cloud】等待扫码超时,请重新运行 workflow")
    sys.exit("[x] 等待扫码超时")


if __name__ == "__main__":
    main()
