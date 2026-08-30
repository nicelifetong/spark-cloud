"""命令行入口:不打开网页也能完成全部操作。

用法:
    python cli.py list                     查看账号列表
    python cli.py run [--account <id>] [--dry] [--friends "张三,李四"] [--messages "🔥|你好"] [--headed]
    python cli.py sync [--account <id>]    仅同步联系人
    python cli.py scan [--account <id>]    仅执行好友抖音号扫描(只读)
    python cli.py serve                    启动 Web 后台(等价 python app.py)

供 GitHub Actions / 计划任务使用:
    python cli.py run --state-b64 <BASE64> --friends "张三" --messages "🔥|今天也要开心哦"
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from keeper import accounts as acc_store, ledger as book, logs as logstore, messages, runner
from keeper.settings import DEFAULT_ACCOUNT, account_dir

logger = logstore.setup()


def _account_id(value: str) -> str:
    return (value or "").strip() or DEFAULT_ACCOUNT


def _import_state_b64(account_id: str, b64: str) -> bool:
    """从 Base64 导入登录态(GitHub Actions 等无文件环境)。"""
    try:
        raw = base64.b64decode(b64.strip())
        d = account_dir(account_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "state.json").write_bytes(raw)
        print(f"[✓] 已从 Base64 导入登录态({len(raw)} 字节) -> {d / 'state.json'}")
        return True
    except Exception as exc:
        print(f"[❌] 登录态导入失败:{exc}")
        return False


def cmd_list() -> None:
    print("当前账号列表:")
    for acc in acc_store.list_accounts():
        mark = "★" if acc["is_default"] else " "
        state = "✓" if acc["state_file_exists"] else "✗"
        print(f"  {mark} {acc['id']:14s} {acc['name']}  启用={acc['enabled']}  登录态={state}")


def cmd_sync(account_id: str) -> None:
    print(f"[*] 正在同步联系人(账号 {account_id})…")
    res = runner.sync_contacts(account_id)
    if not res.get("ok"):
        print(f"[❌] 同步失败:{res.get('reason')}")
        sys.exit(1)
    print(f"[✓] 同步完成:新增 {res.get('added', 0)},更新 {res.get('updated', 0)},共 {res.get('total', 0)}")


def cmd_scan(account_id: str) -> None:
    print(f"[*] 正在扫描好友抖音号(账号 {account_id},只读)…")
    res = runner.run_scan(account_id)
    if not res.get("ok"):
        print(f"[❌] 扫描失败:{res.get('reason')}")
        sys.exit(1)
    print(f"[✓] 扫描完成:采集 {res.get('count', 0)} 条,合并新增 {res.get('added', 0)},升级 {res.get('joined', 0)}")


def cmd_run(account_id: str, dry: bool, only_names: list[str] | None, headed: bool) -> None:
    print(f"[*] 开始运行(账号 {account_id},{'演练模式' if dry else '正式发送'})…")
    res = runner.run_once(account_id, dry=dry, only_names=only_names, headed=headed)
    if not res.get("started"):
        print(f"[❌] 运行失败:{res.get('reason')}")
        sys.exit(1)
    print(f"[✓] 成功 {len(res.get('ok', []))} 人:{', '.join(res.get('ok', [])) or '无'}")
    for item in res.get("failed", []):
        print(f"  ⚠ {item.get('name')}: {item.get('reason')}")
    if res.get("rate_limited"):
        print("[🚨] 触发限流保护,本轮提前熔断")
    if res.get("logged_out"):
        print("[❌] 登录态已过期,请重新扫码")
        sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spark Cloud · 抖音自动续火花 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="查看账号列表")
    p_list.add_argument("--account", default="", help="指定账号(默认 default)")

    p_sync = sub.add_parser("sync", help="同步联系人")
    p_sync.add_argument("--account", default="")

    p_scan = sub.add_parser("scan", help="扫描好友抖音号(只读)")
    p_scan.add_argument("--account", default="")

    p_run = sub.add_parser("run", help="执行一次发送")
    p_run.add_argument("--account", default="")
    p_run.add_argument("--dry", action="store_true", help="演练模式,不真正发送")
    p_run.add_argument("--headed", action="store_true", help="有头浏览器(便于观察)")
    p_run.add_argument("--friends", default="", help="临时指定好友昵称,逗号分隔")
    p_run.add_argument("--messages", default="", help="临时文案池,用 | 分隔")
    p_run.add_argument("--state-b64", default="", help="从 Base64 导入登录态后运行")

    sub.add_parser("serve", help="启动 Web 后台")

    args = parser.parse_args()
    account_id = _account_id(args.account)

    if args.command == "list":
        cmd_list()
    elif args.command == "sync":
        cmd_sync(account_id)
    elif args.command == "scan":
        cmd_scan(account_id)
    elif args.command == "run":
        if args.state_b64 and not _import_state_b64(account_id, args.state_b64):
            sys.exit(1)
        if args.messages.strip():
            cfg = acc_store.load_config(account_id)
            cfg["messages"] = [m.strip() for m in args.messages.split("|") if m.strip()]
            if cfg["messages"]:
                acc_store.save_config(account_id, {"messages": cfg["messages"]})
                print(f"[✓] 已临时设置文案池:{cfg['messages']}")
        only_names = [n.strip() for n in args.friends.split(",") if n.strip()] if args.friends.strip() else None
        cmd_run(account_id, args.dry, only_names, args.headed)
    elif args.command == "serve":
        import app as _app
        _app.main()


if __name__ == "__main__":
    main()
