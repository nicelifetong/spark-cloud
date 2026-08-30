# -*- coding: utf-8 -*-
"""微信 iLink Bot 直连(腾讯官方协议) — 扫码绑定 + 状态推送。

协议参考 weixin-ClawBot-API(github.com/SiverKing/weixin-ClawBot-API),
自研轻量实现:仅 requests + 线程,不依赖 aiohttp/LLM 相关包。

流程:登录线程取二维码 → 轮询扫码状态(支持配对码)→ confirmed 持久化
bot_token → 监听线程 getupdates 长轮询(缓存最后来信联系人的
context_token,主动推送依赖它)→ sendmessage 发送。
ret/errcode == -14 表示令牌过期,需重新扫码。
"""
import base64
import json
import logging
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger("spark")

BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "2.4.6"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = "132102"
BOT_AGENT = "weixin-ClawBot-API/1.2.0 (python)"
API_TIMEOUT = 15
QR_STATUS_TIMEOUT = 35
LISTEN_TIMEOUT = 40
LOGIN_BUDGET = 480          # 单次登录总时长(秒)
VERIFY_WAIT = 300           # 等用户输入配对码(秒)
STALE = -14                 # 令牌过期码
MENU_TTL = 600              # 数字菜单有效期(秒),超时回落主菜单

# 数字菜单:ask = 主菜单;数字在菜单显示后 MENU_TTL 秒内有效
_MENU_TEXTS = {
    "main": (
        "📖 指令导览\n"
        "——————————\n"
        "1. 登录相关\n"
        "2. 账户管理\n"
        "3. 续火/文案\n"
        "——————————\n"
        "回复数字进入对应菜单;发 ask 随时回到本页"),
    "login": (
        "🔐 登录相关\n"
        "——————————\n"
        "1. 开始登录(为当前账户扫码)\n"
        "2. 取消登录\n"
        "0. 返回主菜单\n"
        "——————————\n"
        "提示:首选点开确认链接直接登录,无需扫码"),
    "account": (
        "👤 账户管理\n"
        "——————————\n"
        "1. 所有账户\n"
        "2. 切换账户 → 回复「切换 账户名」\n"
        "3. 新建账户 → 回复「新建 账户名」\n"
        "0. 返回主菜单"),
    "streak": (
        "🔥 续火/文案\n"
        "——————————\n"
        "1. 续火详情\n"
        "2. 好友详情\n"
        "3. 修改自动续火时间 → 回复「时间 HH:MM」\n"
        "4. 自定义发送内容 → 回复「文案查看」\n"
        "0. 返回主菜单"),
}

_TEXT_USAGE = (
    "✏️ 自定义发送内容\n"
    "——————————\n"
    "文案查看 → 看当前全局与好友专属文案\n"
    "文案全部 你好呀 → 所有好友都用这条\n"
    "文案 张三 早上好呀 → 只给张三用这条\n"
    "文案清除 张三 → 张三恢复用全局文案\n"
    "文案恢复默认 → 全局恢复默认文案")


def _client_id():
    return "spark-cloud:%d-%s" % (int(time.time() * 1000), secrets.token_hex(4))


def _qr_svg(content):
    """把扫码内容转成 SVG data-URL(纯 Python,无 PIL 依赖)。"""
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(content, image_factory=qrcode.image.svg.SvgPathImage)
        import io
        buf = io.BytesIO()
        img.save(buf)
        return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _upload_qr(data_url: str) -> str:
    """把二维码图片(data-URL)传到公网临时图床,返回直链;失败返回空串(可选加送链接)。"""
    if not data_url.startswith("data:image/"):
        return ""
    _, _, b64 = data_url.partition(",")
    if not b64:
        return ""
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return ""
    try:
        r = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "1h"},
            files={"fileToUpload": ("qr.png", raw, "image/png")},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        url = (r.text or "").strip()
        return url if url.startswith("http") else ""
    except Exception:
        return ""


class WxBot:
    """线程安全的微信 Bot 会话管理器。"""

    def __init__(self, state_path):
        self.path = Path(state_path)
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._login_thread = None
        self._listen_thread = None
        self._pending_verify = None
        self._menu = ""            # 数字菜单当前层(main/login/account/streak)
        self._menu_at = 0.0        # 菜单显示时间(超时回落主菜单)
        # 运行态(不持久化)
        self.phase = "idle"        # idle/qr_ready/scanned/need_verifycode/bound/expired/error
        self.qr_content = ""
        self.qr_svg = ""
        self.last_error = ""
        self.s = self._load()

    # ---------- 持久化 ----------
    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.s, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    # ---------- 协议底层 ----------
    def _base(self):
        return (self.s.get("baseurl") or BASE_URL).rstrip("/")

    def _headers(self, post=False):
        h = {"iLink-App-Id": ILINK_APP_ID, "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION}
        if post:
            h["Content-Type"] = "application/json"
            h["AuthorizationType"] = "ilink_bot_token"
            h["X-WECHAT-UIN"] = base64.b64encode(str(secrets.randbits(32)).encode()).decode()
            if self.s.get("bot_token"):
                h["Authorization"] = "Bearer " + self.s["bot_token"]
        return h

    @staticmethod
    def _base_info():
        return {"channel_version": CHANNEL_VERSION, "bot_agent": BOT_AGENT}

    def _cgi(self, path, body=None, method="POST", timeout=API_TIMEOUT):
        """调用 CGI;HTTP 200 不代表成功,必须检查 ret/errcode。"""
        url = self._base() + "/" + path.lstrip("/")
        if method == "GET":
            r = requests.get(url, headers=self._headers(False), timeout=timeout)
        else:
            payload = dict(body or {})
            payload.setdefault("base_info", self._base_info())
            r = requests.post(url, headers=self._headers(True), data=json.dumps(payload), timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {}
        ret = data.get("ret", data.get("errcode", 0))
        if r.status_code != 200 or (ret not in (0, None)):
            raise RuntimeError("iLink %s 失败: HTTP %s ret=%s %s" % (
                path.split("?")[0], r.status_code, ret, data.get("errmsg") or data.get("message") or ""))
        return data

    # ---------- 对外接口 ----------
    def status(self):
        with self.lock:
            return {
                "phase": self.phase,
                "bound": self.phase == "bound" and bool(self.s.get("bot_token")),
                "qr_content": self.qr_content,
                "qr_svg": self.qr_svg,
                "need_verifycode": self.phase == "need_verifycode",
                "has_contact": bool(self.s.get("last_contact")),
                "bot_id": self.s.get("ilink_bot_id") or "",
                "last_error": self.last_error,
            }

    def start_login(self):
        with self.lock:
            if self._login_thread and self._login_thread.is_alive():
                return False
            self._stop.clear()
            self.last_error = ""
            self._login_thread = threading.Thread(target=self._login_flow, daemon=True)
            self._login_thread.start()
            return True

    def submit_verify(self, code):
        with self.lock:
            if self.phase != "need_verifycode":
                return False
            self._pending_verify = (code or "").strip()
            return True

    def logout(self):
        with self.lock:
            self._stop.set()
            self.s = {}
            self._save()
            self.phase = "idle"
            self.qr_content = ""
            self.qr_svg = ""
            return True

    def send_wx(self, text):
        """主动推送。接收人必须是给机器人发过消息的联系人(iLink 协议限制)。"""
        with self.lock:
            if not self.s.get("bot_token"):
                return False, "未绑定微信,请先扫码"
            lc = self.s.get("last_contact") or {}
            to_id = lc.get("from_id") or ""
            ctx = lc.get("context_token") or ""
            if not to_id or not ctx:
                return False, "暂无推送目标:请先在微信里给机器人发一条消息"
        try:
            self._typing(ctx, 1)
            body = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_id,
                    "client_id": _client_id(),
                    "message_type": 2,
                    "message_state": 2,
                    "context_token": ctx,
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                }
            }
            self._cgi("ilink/bot/sendmessage", body)
            self._typing(ctx, 2)
            return True, "已发送"
        except RuntimeError as e:
            msg = str(e)
            if "ret=%d" % STALE in msg or "ret=-14" in msg:
                with self.lock:
                    self.phase = "expired"
                    self.last_error = "登录已过期,请重新扫码"
                return False, "登录已过期,请重新扫码"
            return False, msg

    # ---------- 内部流程 ----------
    def _typing(self, context_token, status):
        try:
            cfg = self._cgi("ilink/bot/getconfig", {
                "ilink_user_id": self.s.get("ilink_user_id") or "",
                "context_token": context_token,
            })
            ticket = cfg.get("typing_ticket") or ""
            if not ticket:
                return
            self._cgi("ilink/bot/sendtyping", {
                "ilink_user_id": self.s.get("ilink_user_id") or "",
                "typing_ticket": ticket,
                "status": status,
            })
        except Exception:
            pass  # 输入状态属锦上添花,失败不影响发送

    def _notify(self, stop):
        try:
            self._cgi("ilink/bot/msg/notification" + ("stop" if stop else "start"), {})
        except Exception:
            pass

    def _poll_qr(self, qr, deadline):
        """轮询一张二维码直到终态。返回 confirmed dict / 'expired' / 'timeout'。"""
        verify_sent = False
        verify_deadline = 0
        while time.time() < deadline and not self._stop.is_set():
            try:
                params = "ilink/bot/get_qrcode_status?qrcode=" + quote(qr, safe="")
                if self._pending_verify and not verify_sent:
                    params += "&verify_code=" + quote(self._pending_verify, safe="")
                    verify_sent = True
                    verify_deadline = time.time() + VERIFY_WAIT
                data = self._cgi(params, method="GET", timeout=QR_STATUS_TIMEOUT)
            except RuntimeError as e:
                if "HTTP 200" not in str(e) and "ret=" not in str(e):
                    time.sleep(2)   # 网络抖动:当 wait 处理
                    continue
                raise
            except requests.RequestException:
                continue            # 长轮询超时 → 继续等
            st = (data.get("status") or data.get("state") or "").lower()
            if st in ("wait", ""):
                continue
            if st == "scaned":
                with self.lock:
                    self.phase = "scanned"
                continue
            if st in ("need_verifycode", "verify_code_blocked"):
                with self.lock:
                    self.phase = "need_verifycode"
                    self._pending_verify = None
                while time.time() < verify_deadline and not self._stop.is_set():
                    if self._pending_verify:
                        break
                    time.sleep(1)
                if not self._pending_verify:
                    return "timeout"
                # 带配对码重新轮询(下一圈走 verify_code 分支)
                continue
            if st == "scaned_but_redirect":
                host = data.get("redirect_host") or data.get("redirect") or ""
                if host:
                    with self.lock:
                        self.s["baseurl"] = "https://" + host.replace("https://", "").rstrip("/")
                        self._save()
                    return "redirect"
                continue
            if st == "binded_redirect":
                # 本地令牌已绑定该机器人,直接复用
                if self.s.get("bot_token"):
                    return self.s
                continue
            if st in ("confirmed", "confirm"):
                return data
            if st == "expired":
                time.sleep(2)   # 换码小间隔,防服务端风控
                return "expired"
        return "timeout"

    def _login_flow(self):
        deadline = time.time() + LOGIN_BUDGET
        try:
            for attempt in range(3):
                if self._stop.is_set():
                    return
                r = self._cgi("ilink/bot/get_bot_qrcode?bot_type=3", {"local_token_list": []})
                token = r.get("qrcode") or ""
                if not token:
                    raise RuntimeError("二维码响应缺少 qrcode 字段")
                # 官方协议:轮询用 qrcode 字段;qrcode_img_content 仅作展示(可能缺失)
                disp = r.get("qrcode_img_content") or token
                with self.lock:
                    self.qr_content = disp
                    self.qr_svg = disp if disp.startswith("data:") else _qr_svg(disp)
                    self.phase = "qr_ready"
                res = self._poll_qr(token, min(deadline, time.time() + 160))
                if isinstance(res, dict):
                    with self.lock:
                        self.s["bot_token"] = res.get("bot_token") or self.s.get("bot_token")
                        if res.get("baseurl"):
                            self.s["baseurl"] = res["baseurl"]
                        self.s["ilink_bot_id"] = res.get("ilink_bot_id") or self.s.get("ilink_bot_id") or ""
                        self.s["ilink_user_id"] = res.get("ilink_user_id") or self.s.get("ilink_user_id") or ""
                        self._save()
                        self.phase = "bound"
                        self.qr_content = ""
                        self.qr_svg = ""
                    self._notify(stop=False)
                    self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
                    self._listen_thread.start()
                    return
                if res == "redirect":
                    continue            # 换节点后重新取二维码
                if res == "expired":
                    continue            # 二维码过期,换下一张
                # timeout
                break
            with self.lock:
                self.phase = "error"
                self.last_error = "登录超时,请重试"
        except Exception as e:
            with self.lock:
                self.phase = "error"
                self.last_error = str(e)

    # ---------- 微信指令:「登录」→ 抖音扫码登录,二维码推送到微信 ----------
    def _handle_login_command(self):
        try:
            old = getattr(self, "_login_watch", None)
            if old and old.is_alive():
                from . import qrlogin
                old_aid = getattr(self, "_login_watch_aid", "") or ""
                st = qrlogin.poll(old_aid) if old_aid else {}
                if (st or {}).get("status") == "waiting":
                    self.send_wx(
                        "登录流程仍在进行中,请查看上面推送的二维码消息:\n"
                        "首选点开确认链接直接登录;或用另一台设备打开\n"
                        "二维码图片链接对屏实时扫(相册识别会被风控,不要用)\n"
                        "如要重新开始,请发送「取消登录」")
                    return
                if old_aid:
                    qrlogin.cancel(old_aid)
                old.join(timeout=5)
            from .accounts import list_accounts
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            target = self._effective_account(accs)
            if target is None:
                self.send_wx("未找到任何账号,请先在网页端创建账号")
                return
            aid = target["id"]
            name = target.get("name") or aid
            from . import qrlogin
            res = qrlogin.start(aid)
            if not res.get("ok"):
                self.send_wx("发起登录失败: " + str(res.get("error") or res.get("message") or "未知错误"))
                return
            self.send_wx(f"正在为账号「{name}」生成抖音登录二维码,请稍候…")
            self._login_watch_aid = aid
            self._login_watch = threading.Thread(
                target=self._watch_qrlogin, args=(aid, name), daemon=True)
            self._login_watch.start()
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"登录指令处理失败: {e}")
            except Exception:
                pass

    def _handle_cancel_command(self):
        try:
            from . import qrlogin
            old = getattr(self, "_login_watch", None)
            if not (old and old.is_alive()):
                self.send_wx("当前没有进行中的登录流程")
                return
            qrlogin.cancel(getattr(self, "_login_watch_aid", "") or "")
            # watch 线程会在下轮 poll 看到 canceled,自行收尾并通知
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"取消失败: {e}")
            except Exception:
                pass

    # ---------- 微信指令:账户管理与导览 ----------
    def _effective_account(self, accs):
        """微信侧当前操作的账户:显式切换过用之;否则未登录优先、再取第一个。"""
        with self.lock:
            cur = (self.s.get("wx_account") or "").strip()
        for a in accs:
            if a["id"] == cur:
                return a
        from .settings import account_dir
        for a in accs:
            if not (account_dir(a["id"]) / "state.json").exists():
                return a
        return accs[0] if accs else None

    def _handle_list_accounts(self):
        try:
            from .accounts import list_accounts
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            if not accs:
                self.send_wx("还没有任何账户,发送「新建xx账户」创建")
                return
            cur = self._effective_account(accs)
            cur_id = (cur or {}).get("id", "")
            lines = [f"共有 {len(accs)} 个账户(✅ = 当前操作账户):"]
            for i, a in enumerate(accs, 1):
                mark = " ✅" if a["id"] == cur_id else ""
                login = "已登录" if a.get("state_file_exists") else "未登录"
                lines.append(f"{i}. {a.get('name') or a['id']}{mark} [{login}]")
            lines.append("切换:发送「切换到xx账户」;新建:发送「新建xx账户」")
            self.send_wx("\n".join(lines))
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"查询账户失败: {e}")
            except Exception:
                pass

    def _handle_switch_account(self, name):
        try:
            from .accounts import list_accounts
            key = (name or "").strip()
            if not key:
                self.send_wx("用法:切换到xx账户(如:切换到小号1账户)")
                return
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            target = next((a for a in accs
                           if (a.get("name") or "") == key or a["id"] == key), None)
            if target is None:
                hits = [a for a in accs
                        if key in (a.get("name") or "") or key in a["id"]]
                target = hits[0] if len(hits) == 1 else None
            if target is None:
                self.send_wx(f"没有找到账户「{key}」。发送「所有账户」查看列表")
                return
            with self.lock:
                self.s["wx_account"] = target["id"]
                self._save()
            self.send_wx(
                f"已切换到账户「{target.get('name') or target['id']}」✅\n"
                "之后的「登录」等操作都将针对该账户")
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"切换失败: {e}")
            except Exception:
                pass

    def _handle_create_account(self, name):
        try:
            from .accounts import create
            meta = create(name or "")
            with self.lock:
                self.s["wx_account"] = meta["id"]
                self._save()
            self.send_wx(
                f"账户「{meta['name']}」({meta['id']})创建成功,已切换为当前账户 ✅\n"
                "发送「登录」为它登录抖音")
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"新建账户失败: {e}")
            except Exception:
                pass

    def _handle_set_time(self, arg):
        """「时间 HH:MM」:修改当前账户的自动续火时间。"""
        try:
            from .accounts import list_accounts, save_config
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            acc = self._effective_account(accs)
            if not acc:
                self.send_wx("还没有任何账户,发送「新建xx账户」创建")
                return
            t = (arg or "").strip().replace("：", ":")
            if not t:
                self.send_wx("用法:时间 HH:MM(如:时间 20:30)")
                return
            aid, name = acc["id"], acc.get("name") or acc["id"]
            cfg = save_config(aid, {"schedule_time": t})
            auto = "开" if cfg.get("auto_enabled") else "关"
            self.send_wx(
                f"⏰ 账户「{name}」自动续火时间已改为每天 "
                f"{cfg.get('schedule_time')} ✅\n自动续火开关:{auto}(开关请在网页端设置页操作)")
        except ValueError:
            self.send_wx("时间格式不对。用法:时间 HH:MM(如:时间 20:30)")
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"修改时间失败: {e}")
            except Exception:
                pass

    def _resolve_friend(self, aid, key):
        """台账里解析好友名:全名精确 → 唯一包含匹配;失败返回空串。"""
        try:
            from . import ledger as book
            names = [str(e.get("name") or "").strip()
                     for e in (book.load(aid) or []) if str(e.get("name") or "").strip()]
        except Exception:  # noqa: BLE001
            return ""
        if key in names:
            return key
        hits = [n for n in names if key in n]
        return hits[0] if len(hits) == 1 else ""

    def _wx_show_texts(self, aid, name):
        from .accounts import load_config
        cfg = load_config(aid) or {}
        msgs = [str(m) for m in (cfg.get("messages") or []) if str(m).strip()]
        lines = [f"✏️ 账户「{name}」的发送内容", "——————————", "全局(所有人):"]
        lines += ([f"{i + 1}. {m}" for i, m in enumerate(msgs)] or ["(空)"])
        lines.append("——————————")
        ov = {k: v for k, v in (cfg.get("friend_overrides") or {}).items()
              if [str(x) for x in ((v or {}).get("pool") or []) if str(x).strip()]}
        if ov:
            lines.append("好友专属:")
            for k, v in ov.items():
                pool = [str(x) for x in v.get("pool") if str(x).strip()]
                lines.append(f"• {k}: {' | '.join(pool)}")
        else:
            lines.append("好友专属:无(全员用全局文案)")
        self.send_wx("\n".join(lines))

    def _handle_set_text(self, arg):
        """「文案…」:自定义发送内容(全部应用/指定联系人)。"""
        arg = (arg or "").strip().replace("\u3000", " ")
        if not arg:
            self.send_wx(_TEXT_USAGE)
            return
        try:
            from .accounts import list_accounts, load_config, save_config
            from .settings import DEFAULT_CONFIG
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            acc = self._effective_account(accs)
            if not acc:
                self.send_wx("还没有任何账户,发送「新建xx账户」创建")
                return
            aid, name = acc["id"], acc.get("name") or acc["id"]
            if arg == "查看":
                return self._wx_show_texts(aid, name)
            cfg = load_config(aid) or {}
            ov = dict(cfg.get("friend_overrides") or {})
            if arg.startswith("全部 "):
                text = arg[len("全部 "):].strip()
                if not text:
                    self.send_wx("用法:文案全部 你的内容")
                    return
                save_config(aid, {"messages": [text]})
                self.send_wx(f"✅ 账户「{name}」所有好友的发送内容已改为:\n{text}"
                             "\n\n(原全局多条文案已被替换;好友专属文案不受影响,"
                             "如需清理请发「文案清除 好友名」)")
                return
            if arg == "恢复默认":
                newcfg = save_config(aid, {"messages": list(DEFAULT_CONFIG.get("messages") or ["🔥 续火花"])})
                self.send_wx("✅ 全局文案已恢复默认:\n" +
                             "\n".join(f"{i + 1}. {m}" for i, m in enumerate(newcfg.get("messages") or [])))
                return
            if arg.startswith("清除 "):
                key = arg[len("清除 "):].strip()
                if not key:
                    self.send_wx("用法:文案清除 好友名")
                    return
                if key == "全部":
                    left = {k: v for k, v in ov.items()
                            if not [str(x) for x in ((v or {}).get("pool") or []) if str(x).strip()]}
                    save_config(aid, {"friend_overrides": left})
                    self.send_wx("✅ 已清除所有好友专属文案,全员恢复使用全局文案")
                    return
                resolved = self._resolve_friend(aid, key)
                if not resolved:
                    self.send_wx(f"没有找到好友「{key}」。发送「好友详情」查看列表")
                    return
                if resolved not in ov or not [str(x) for x in ((ov[resolved] or {}).get("pool") or []) if str(x).strip()]:
                    self.send_wx(f"好友「{resolved}」没有专属文案,已在用全局文案")
                    return
                ov.pop(resolved, None)
                save_config(aid, {"friend_overrides": ov})
                self.send_wx(f"✅ 好友「{resolved}」的专属文案已清除,恢复使用全局文案")
                return
            head, _, text = arg.partition(" ")
            text = text.strip()
            if not text:
                self.send_wx(_TEXT_USAGE)
                return
            resolved = self._resolve_friend(aid, head)
            if not resolved:
                self.send_wx(f"没有找到好友「{head}」。发送「好友详情」查看列表\n"
                             "若想给所有人设置,请用:文案全部 内容")
                return
            rule = dict(ov.get(resolved) or {})
            rule["pool"] = [text]
            ov[resolved] = rule
            save_config(aid, {"friend_overrides": ov})
            self.send_wx(f"✅ 好友「{resolved}」的专属发送内容已设为:\n{text}")
        except ValueError as e:
            self.send_wx(f"设置失败: {e}")
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"设置文案失败: {e}")
            except Exception:
                pass

    def _menu_active(self):
        """当前有效菜单层(超过 MENU_TTL 视为过期)。"""
        key = getattr(self, "_menu", "")
        at = getattr(self, "_menu_at", 0.0)
        return key if key and (time.time() - at) <= MENU_TTL else ""

    def _show_menu(self, key):
        """显示菜单并记录层级/时间。"""
        text = _MENU_TEXTS.get(key) or _MENU_TEXTS["main"]
        self._menu = key if key in _MENU_TEXTS else "main"
        self._menu_at = time.time()
        self.send_wx(text)

    def _handle_menu_digit(self, d):
        """数字菜单:按当前层级分发;执行完动作后重现所在菜单。"""
        try:
            cur = self._menu_active()
            if not cur or d == "0":
                self._show_menu("main")
                return
            if cur == "main":
                if d in ("1", "2", "3"):
                    self._show_menu({"1": "login", "2": "account", "3": "streak"}[d])
                else:
                    self.send_wx(f"没有选项 {d},请回复 1/2/3")
                    self._show_menu("main")
                return
            if cur == "login":
                if d == "1":
                    self._handle_login_command()
                elif d == "2":
                    self._handle_cancel_command()
                else:
                    self.send_wx(f"没有选项 {d}")
                self._show_menu("login")
                return
            if cur == "account":
                if d == "1":
                    self._handle_list_accounts()
                elif d == "2":
                    self.send_wx("请直接回复:切换 账户名(如:切换 小号一)\n发送「所有账户」可查看列表")
                elif d == "3":
                    self.send_wx("请直接回复:新建 账户名(如:新建 小号二)")
                else:
                    self.send_wx(f"没有选项 {d}")
                self._show_menu("account")
                return
            if cur == "streak":
                if d == "1":
                    self._handle_streak_detail()
                elif d == "2":
                    self._handle_friends_detail()
                elif d == "3":
                    self.send_wx("请直接回复:时间 HH:MM(如:时间 20:30)\n当前设置可发「续火详情」查看")
                elif d == "4":
                    self.send_wx(_TEXT_USAGE)
                else:
                    self.send_wx(f"没有选项 {d}")
                self._show_menu("streak")
                return
            self._show_menu("main")
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"菜单操作失败: {e}")
            except Exception:
                pass

    def _handle_ask(self):
        self._show_menu("main")

    def _handle_streak_detail(self):
        """「续火详情」:当前账户的续火状态、进程与上次运行结果。"""
        try:
            from datetime import datetime as _dt
            from .accounts import list_accounts, load_config
            from . import runner, runtime as rt, ledger as book
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            acc = self._effective_account(accs)
            if not acc:
                self.send_wx("还没有任何账户,发送「新建xx账户」创建")
                return
            aid, name = acc["id"], acc.get("name") or acc["id"]
            info = rt.load(aid)
            busy = runner.is_busy(aid) or bool(info.get("running"))
            try:
                cfg = load_config(aid) or {}
            except Exception:
                cfg = {}
            sess = {"ok": "✅ 正常", "partial": "🟡 部分成功", "failed": "❌ 上轮失败",
                    "expired": "🔒 登录已过期"}.get(
                        str(info.get("session_status") or "unknown"), "❓ 未知")
            entries = book.load(aid)
            sel = [e for e in entries if e.get("selected")]
            top = max(entries, key=lambda e: (e.get("days") or 0)) if entries else None
            jit = cfg.get("jitter_minutes", 0)
            lines = [
                f"【{name}】续火详情",
                f"进程: {'⏳ 任务运行中' if busy else '💤 空闲'}",
                f"登录态: {sess}",
                f"自动续火: {'开' if cfg.get('auto_enabled') else '关'}"
                f"(每天 {cfg.get('schedule_time') or '21:00'}"
                + (f" ±{jit} 分钟)" if jit else ")"),
                f"发送目标: 已选 {len(sel)} 人"
                + (f",单轮上限 {cfg.get('max_per_run')}" if cfg.get("max_per_run") else ""),
                f"好友台账: 共 {len(entries)} 人"
                + (f",最高 🔥{top.get('days', 0)} 天({top.get('name')})" if top else ""),
            ]
            last = info.get("last_run") or {}
            if last:
                flags = [t for t, k in (("演练模式", "dry_run"), ("触发限流", "rate_limited"),
                                        ("登录失效", "logged_out")) if last.get(k)]
                skipped = len(last.get("skipped") or [])
                note = str(last.get("note") or "")
                lines.append(
                    f"上次运行: {str(last.get('at') or '?')[:16]} "
                    f"成功 {len(last.get('ok') or [])} / 失败 {len(last.get('failed') or [])}"
                    + (f" / 跳过 {skipped}" if skipped else "")
                    + (f"({'、'.join(flags)})" if flags else "")
                    + (f" [{note}]" if note else ""))
            else:
                lines.append("上次运行: 从未运行")
            b = info.get("b_channel") or {}
            if b.get("date") == _dt.now().astimezone().date().isoformat() and b.get("count"):
                lines.append(f"今日首条私信: 已发 {b['count']} 条")
            lines.append("联系人同步: " + (str(info.get("contacts_at"))[:16] if info.get("contacts_at") else "从未")
                         + (f"(错误: {info.get('contacts_error')})" if info.get("contacts_error") else ""))
            self.send_wx("\n".join(lines))
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"查询续火详情失败: {e}")
            except Exception:
                pass

    def _handle_friends_detail(self):
        """「好友详情」:当前账户全部好友 + 火花天数,按天数降序。"""
        try:
            from .accounts import list_accounts
            from . import ledger as book
            accs = [a for a in (list_accounts() or []) if a.get("id")]
            acc = self._effective_account(accs)
            if not acc:
                self.send_wx("还没有任何账户,发送「新建xx账户」创建")
                return
            aid, name = acc["id"], acc.get("name") or acc["id"]
            entries = sorted(book.load(aid), key=lambda e: -(e.get("days") or 0))
            if not entries:
                self.send_wx(f"【{name}】好友台账为空。请先在网页端「同步联系人」")
                return
            sel = sum(1 for e in entries if e.get("selected"))
            cap = 40
            lines = [f"【{name}】好友详情(共 {len(entries)} 人,已选 {sel} 人,按火花天数排序)"]
            for i, e in enumerate(entries[:cap], 1):
                lines.append(f"{i}. {e['name']} 🔥{e.get('days', 0)} 天"
                             + (" ✅" if e.get("selected") else ""))
            if len(entries) > cap:
                lines.append(f"…其余 {len(entries) - cap} 人请看网页端")
            self.send_wx("\n".join(lines))
        except Exception as e:  # noqa: BLE001
            try:
                self.send_wx(f"查询好友详情失败: {e}")
            except Exception:
                pass

    def _push_qr(self, aid, name, face=False):
        """把当前二维码推到微信:确认链接(首选)+ 图床二维码图。"""
        from . import qrlogin
        qr = qrlogin.poll(aid) or {}
        links = []
        # 登录码:确认链接直接点开(抖音对相册识别登录码有风控,扫码走不通);
        # 刷脸码:不解析链接(截图即可直接扫),只推图床二维码图
        confirm = "" if face else (qrlogin.qr_content(aid) or "").strip()
        if confirm.startswith("http"):
            links.append(f"👉 {confirm}  (推荐:点开直接确认登录,无需扫码)")
        img = _upload_qr(qr.get("qrcode") or "")
        if img:
            # catbox 的 Cloudflare 按 UA 拦截微信内置浏览器(MicroMessenger→403),
            # 经 wsrv.nl 图片代理中转(实测国内网络+微信UA均 200)才可直开
            bed = f"https://wsrv.nl/?url={quote(img, safe='')}"
            links.append(f"👉 {bed}  (二维码图,任意网络)")
        body = "\n".join(links)
        if face:
            self.send_wx(
                f"【{name}】⚠ 触发安全验证(刷脸)\n{body}\n\n"
                "用【另一台设备】打开二维码链接实时扫,\n"
                "或直接【截图】后相册识别——刷脸码截图可直接扫")
        else:
            self.send_wx(
                f"【{name}】抖音登录二维码已生成 ✅\n\n{body}\n\n"
                "首选:点确认链接,在抖音里点「确认登录」;\n"
                "备用:用另一台设备打开二维码链接,抖音「扫一扫」对屏实时扫\n"
                "(相册识别登录码会被风控,不要用)\n"
                "登录结果会在这里通知你")

    def _watch_qrlogin(self, aid, name):
        """监视 qrlogin 状态,把二维码(字符画)/人脸验证/结果推送到微信。"""
        from . import qrlogin
        sent_qr = ""
        sent_status = ""
        deadline = time.time() + 330
        while time.time() < deadline:
            try:
                st = qrlogin.poll(aid) or {}
                status = st.get("status") or ""
                msg = st.get("message") or ""
                qr = st.get("qrcode") or ""
                if status == "waiting" and qr and qr != sent_qr:
                    sent_qr = qr
                    self._push_qr(aid, name,
                                  face=("验证" in msg or "人脸" in msg))
                elif status == "done" and sent_status != "done":
                    self.send_wx(f"【{name}】登录成功 ✅ 登录态已保存")
                    return
                elif status in ("expired", "failed", "canceled") and sent_status != status:
                    reason = {"expired": "扫码超时/二维码过期",
                              "failed": "会话异常: " + (st.get("error") or "未知"),
                              "canceled": "已取消"}.get(status, msg)
                    self.send_wx(f"【{name}】登录未完成({reason})。可重新发送「登录」再试")
                    return
            except Exception:  # noqa: BLE001 单次失败不影响整个监听
                logger.exception("watch_qrlogin 轮询/推送异常")
            time.sleep(2)

    def _listen_loop(self):
        while not self._stop.is_set():
            with self.lock:
                if not self.s.get("bot_token"):
                    return
                cursor = self.s.get("get_updates_buf") or ""
            try:
                data = self._cgi("ilink/bot/getupdates", {
                    "get_updates_buf": cursor,
                    "base_info": self._base_info(),
                }, timeout=LISTEN_TIMEOUT)
            except RuntimeError as e:
                if "ret=%d" % STALE in str(e) or "ret=-14" in str(e):
                    with self.lock:
                        self.phase = "expired"
                        self.last_error = "登录已过期,请重新扫码"
                    return
                time.sleep(3)
                continue
            except requests.RequestException:
                continue    # 长轮询超时,正常
            except Exception:  # noqa: BLE001 畸形响应等意外错误,退避重试不杀线程
                logger.exception("listen_loop 轮询异常")
                time.sleep(3)
                continue
            try:
                with self.lock:
                    new_cursor = data.get("get_updates_buf")
                    if new_cursor:
                        self.s["get_updates_buf"] = new_cursor
                    msgs = data.get("msgs") or []
                    for m in msgs:
                        fid = m.get("from_user_id") or m.get("from_id") or ""
                        ctx = m.get("context_token") or ""
                        if fid and ctx:
                            self.s["last_contact"] = {"from_id": fid, "context_token": ctx, "at": int(time.time())}
                        txt = _msg_text(m).strip()
                        if not txt:
                            continue
                        # 消息去重:游标未推进/服务端重发/多进程轮询时,
                        # 同一条消息只执行一次,否则数字菜单会一直弹
                        key = _msg_key(m, fid, txt)
                        if key:
                            seen = self.s.get("seen_msgs") or {}
                            if key in seen:
                                continue
                            seen[key] = time.time()
                            if len(seen) > 400:   # 只留最近 400 条,防无限膨胀
                                seen = dict(sorted(seen.items(), key=lambda kv: kv[1])[-200:])
                            self.s["seen_msgs"] = seen
                        if txt == "登录":
                            threading.Thread(target=self._handle_login_command, daemon=True).start()
                        elif txt in ("取消登录", "取消"):
                            threading.Thread(target=self._handle_cancel_command, daemon=True).start()
                        elif txt == "所有账户":
                            threading.Thread(target=self._handle_list_accounts, daemon=True).start()
                        elif txt.startswith("切换到") and txt.endswith("账户"):
                            _name = txt[len("切换到"):-len("账户")].strip()
                            threading.Thread(target=self._handle_switch_account,
                                             args=(_name,), daemon=True).start()
                        elif txt.startswith("新建") and txt.endswith("账户"):
                            _name = txt[len("新建"):-len("账户")].strip()
                            threading.Thread(target=self._handle_create_account,
                                             args=(_name,), daemon=True).start()
                        elif txt.startswith("切换 ") and txt[len("切换 "):].strip():
                            threading.Thread(target=self._handle_switch_account,
                                             args=(txt[len("切换 "):].strip(),), daemon=True).start()
                        elif txt.startswith("新建 ") and txt[len("新建 "):].strip():
                            threading.Thread(target=self._handle_create_account,
                                             args=(txt[len("新建 "):].strip(),), daemon=True).start()
                        elif txt.isdigit() and len(txt) <= 2:
                            threading.Thread(target=self._handle_menu_digit,
                                             args=(txt,), daemon=True).start()
                        elif txt in ("续火详情", "续火状态"):
                            threading.Thread(target=self._handle_streak_detail, daemon=True).start()
                        elif txt in ("好友详情", "好友列表"):
                            threading.Thread(target=self._handle_friends_detail, daemon=True).start()
                        elif txt.startswith("修改时间 ") and txt[len("修改时间 "):].strip():
                            threading.Thread(target=self._handle_set_time,
                                             args=(txt[len("修改时间 "):].strip(),), daemon=True).start()
                        elif txt.startswith("时间 ") and txt[len("时间 "):].strip():
                            threading.Thread(target=self._handle_set_time,
                                             args=(txt[len("时间 "):].strip(),), daemon=True).start()
                        elif txt.startswith("文案"):
                            threading.Thread(target=self._handle_set_text,
                                             args=(txt[len("文案"):],), daemon=True).start()
                        elif txt.lower() == "ask":
                            threading.Thread(target=self._handle_ask, daemon=True).start()
                    self._save()
            except Exception:  # noqa: BLE001 单条消息/落盘失败不杀监听线程
                logger.exception("listen_loop 消息处理异常")


def _msg_key(m: dict, fid: str, txt: str) -> str:
    """消息去重键:优先服务端消息 id,退化为 发件人|时间戳|文本;都不足则不去重。"""
    for f in ("msg_id", "client_msg_id", "id"):
        v = str(m.get(f) or "").strip()
        if v:
            return "id:" + v
    ct = str(m.get("create_time") or m.get("timestamp") or m.get("time") or "").strip()
    if ct:
        return f"t:{fid}|{ct}|{txt}"
    return ""


def _msg_text(m: dict) -> str:
    """宽容提取消息文本(item_list[].text_item.text,兼容顶层 text)。"""
    try:
        for it in (m.get("item_list") or []):
            t = ((it or {}).get("text_item") or {}).get("text")
            if t:
                return str(t)
    except Exception:
        pass
    return str(m.get("text") or "")


# 全局单例:状态文件放在 data/ 下(web.py 初始化时创建)
wxbot = None


def init_wxbot(data_dir):
    global wxbot
    if wxbot is None:
        wxbot = WxBot(Path(data_dir) / "wx_state.json")
        if wxbot.s.get("bot_token"):
            wxbot.phase = "bound"
            wxbot._listen_thread = threading.Thread(target=wxbot._listen_loop, daemon=True)
            wxbot._listen_thread.start()
    return wxbot
