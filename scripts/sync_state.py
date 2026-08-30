"""一键把本机登录态上传到云服务器(SSH/SFTP,基于 paramiko)。

用法: python scripts/sync_state.py
交互式输入服务器 IP/用户名/端口/密码后自动上传 data/accounts/default/state.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from keeper.settings import account_dir

LOCAL_STATE = account_dir("default") / "state.json"


def _web_port() -> str:
    """读取项目 .env 中的端口(Docker 部署优先 SPARK_WEB_PORT,本地部署 SPARK_PORT)。"""
    try:
        env = Path(__file__).resolve().parent.parent / ".env"
        vals = {}
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
        return vals.get("SPARK_WEB_PORT") or vals.get("SPARK_PORT") or "8000"
    except Exception:
        return "8000"


def main() -> None:
    print("=" * 60)
    print("  🔥 Spark Cloud · 同步登录态到服务器")
    print("=" * 60)
    if not LOCAL_STATE.exists():
        print("[❌] 本机未找到登录态,请先运行 scripts/1.提取登录态.bat")
        input("按回车退出…")
        sys.exit(1)
    print(f"[✓] 本机登录态: {LOCAL_STATE} ({LOCAL_STATE.stat().st_size} 字节)")

    host = input("👉 服务器 IP: ").strip()
    if not host:
        sys.exit("服务器 IP 不能为空")
    user = input("👉 SSH 用户名 [root]: ").strip() or "root"
    port = int(input("👉 SSH 端口 [22]: ").strip() or "22")
    remote = input("👉 远程项目路径 [/opt/spark-cloud]: ").strip() or "/opt/spark-cloud"
    password = input("🔑 服务器密码(明文可见,可粘贴): ").strip()

    try:
        import paramiko
    except ImportError:
        sys.exit("[❌] 缺少 paramiko,请先 pip install -r requirements.txt")

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port=port, username=user, password=password, timeout=15, banner_timeout=15, auth_timeout=15)
        remote_dir = remote.rstrip("/") + "/data/accounts/default"
        ssh.exec_command(f"mkdir -p '{remote_dir}'")[1].channel.recv_exit_status()
        sftp = ssh.open_sftp()
        sftp.put(str(LOCAL_STATE), remote_dir + "/state.json")
        sftp.close()
        ssh.close()
        print(f"[✓] 上传成功 → {remote_dir}/state.json")
        print(f"    浏览器打开 http://{host}:{_web_port()} 即可使用")
    except Exception as exc:
        print(f"[❌] 上传失败:{exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
