"""一键把整个项目打包部署到云服务器(SSH,基于 paramiko)。

用法: python scripts/deploy_remote.py
交互式输入服务器信息后:上传代码(排除 data/.venv/__pycache__) → 远程执行 deploy/deploy.sh。
"""
from __future__ import annotations

import io
import shlex
import sys
import traceback
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {"data", ".venv", "venv", "__pycache__", ".git", "_smoke", "scripts"}
EXCLUDE_EXTS = {".pyc", ".log"}
EXCLUDE_FILES = {".env"}          # 服务器配置本地化,不能被本地 .env 覆盖


def build_bundle() -> bytes:
    """把项目打包成内存 zip(自动排除敏感/大文件)。"""
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in BASE.rglob("*"):
            if path.is_dir() or any(part in EXCLUDE_DIRS for part in path.relative_to(BASE).parts):
                continue
            if path.suffix in EXCLUDE_EXTS or path.name in EXCLUDE_FILES:
                continue
            zf.write(path, path.relative_to(BASE).as_posix())
            count += 1
    print(f"[✓] 已打包 {count} 个文件")
    return buf.getvalue()


def main() -> None:
    print("=" * 60)
    print("  🔥 Spark Cloud · 一键部署到云服务器")
    print("=" * 60)
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

    bundle = build_bundle()
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port=port, username=user, password=password, timeout=15, banner_timeout=15, auth_timeout=15)

        # ---------- 权限探测:root 直跑;非 root 自动 sudo 提权 ----------
        def _run_out(cmd, timeout=30):
            _in, o, e = ssh.exec_command(cmd, timeout=timeout)
            o.channel.recv_exit_status()
            return (o.read() or b"").decode(errors="replace").strip()

        is_root = _run_out("id -u") == "0"
        sudo_prefix = ""
        sudo_password = None
        if not is_root:
            if _run_out("sudo -n true 2>/dev/null && echo Y") == "Y":
                sudo_prefix = "sudo -n "
                print("[*] 非 root 账号,使用免密 sudo 提权")
            else:
                sudo_prefix = "sudo -S -p '' "
                sudo_password = password
                print("[*] 非 root 账号,将用你输入的密码 sudo 提权")

        def run(cmd, timeout=120):
            """远程执行(自动提权);返回 (stdout, stderr)。"""
            full = f"{sudo_prefix}bash -c {shlex.quote(cmd)}"
            _in, o, e = ssh.exec_command(full, timeout=timeout)
            if sudo_password is not None:
                _in.write(sudo_password + "\n")
                _in.flush()
            o.channel.recv_exit_status()
            return (o.read() or b"").decode(errors="replace").strip(), \
                   (e.read() or b"").decode(errors="replace").strip()

        # ---------- 预检1: 远程目录(带提权重试) ----------
        r_dir = shlex.quote(remote)
        out, err = run(f"mkdir -p {r_dir} && cd {r_dir} && pwd")
        if not out:
            sys.exit(
                f"[❌] 无法创建远程目录 {remote!r}: {err or '权限不足'}\n"
                "    解决: ① SSH 用户名改用 root 重跑; 或 ② 确认该账号有 sudo 权限")
        print(f"[✓] 远程目录: {out}")

        # ---------- 预检2: unzip 缺失则自动安装(Debian/Ubuntu) ----------
        out, _ = run("command -v unzip || (apt-get update -y && apt-get install -y unzip) || echo MISSING")
        if out in ("", "MISSING"):
            print("[⚠] 远程缺少 unzip 且自动安装失败,请手动安装: apt-get install -y unzip")

        # ---------- 上传到家目录(SFTP 以登录用户身份写入,避免 root 目录写不进) ----------
        sftp = ssh.open_sftp()
        home = _run_out("echo $HOME") or "/tmp"
        staged = home.rstrip("/") + "/bundle.zip"
        sftp.putfo(io.BytesIO(bundle), staged)
        sftp.stat(staged)  # 上传后校验,防伪成功
        sftp.close()
        print(f"[✓] 代码上传完成({len(bundle) // 1024} KB),开始远程部署…")

        # ---------- 探测部署方式:服务器有 Docker → compose 构建;否则系统直装 ----------
        # PATH 补上 snap/本地安装常见路径,避免 sudo secure_path 找不到 docker
        docker_out, _ = run(
            'export PATH="/usr/local/bin:/snap/bin:/opt/bin:$PATH"; '
            "command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && echo Y || echo N")
        docker_ok = (docker_out == "Y")      # 必须归一化:字符串"N"也是真值!
        # 无论走哪条路,先停掉可能残留的系统直装服务(防 8000 端口冲突;静默)
        run("systemctl stop spark-cloud 2>/dev/null; systemctl disable spark-cloud 2>/dev/null; true")
        if docker_ok:
            print("[*] 服务器有 Docker → Docker Compose 模式(构建镜像并启动)")
        else:
            print("[*] 未检测到 Docker → 系统直装(systemd)模式")

        r_stage = shlex.quote(staged)
        deploy_cmd = ("docker compose up -d --build && docker compose ps" if docker_ok
                      else "bash deploy/deploy.sh")
        cmd = (f"mv {r_stage} {r_dir}/bundle.zip && cd {r_dir} && "
               f"unzip -o bundle.zip -d . && rm -f bundle.zip && {deploy_cmd}")
        # timeout=60:单次读静默 60 秒就抛超时 → 由下面的循环当"心跳"处理,
        # 而不是直接放弃(pip 静默装包/下载 Chromium 时长时间无输出是正常的)
        _in, stdout, stderr = ssh.exec_command(
            f"{sudo_prefix}bash -c {shlex.quote(cmd)}", timeout=60)
        if sudo_password is not None:
            _in.write(sudo_password + "\n")
            _in.flush()
        import time as _time
        deadline = _time.time() + 2700  # 总耐心 45 分钟
        while True:
            try:
                line = stdout.readline()
            except (TimeoutError, OSError):
                if _time.time() > deadline:
                    print("\n[⚠] 等待超过 45 分钟,本机放弃监听;"
                          "远端可能仍在安装,稍后可直接访问网页确认")
                    break
                print(".", end="", flush=True)  # 心跳:远端还在忙
                continue
            if line == "":
                break  # EOF:远端命令结束
            print(line, end="")
        # 等远程命令真正退出再判码(最多 10s;不能 race——刚跑完时状态可能还没就绪)
        _code = None
        for _ in range(100):
            if stdout.channel.exit_status_ready():
                _code = stdout.channel.recv_exit_status()
                break
            import time as _t
            _t.sleep(0.1)
        if _code is not None and _code != 0:
            print(f"[❌] 远程部署命令退出码 {_code}")
            sys.exit(1)
        if docker_ok:
            # Docker 模式收尾:等健康检查通过;通不过就如实报错并打印诊断
            port, _ = run(f"cd {r_dir} && grep '^SPARK_WEB_PORT=' .env 2>/dev/null | cut -d= -f2- | tr -d '\\r\\n'")
            port = port or "8000"
            tok, _ = run(f"cd {r_dir} && grep '^SPARK_TOKEN=' .env 2>/dev/null | cut -d= -f2- | tr -d '\\r\\n'")
            print("[*] 等待容器健康检查…")
            healthy = False
            for _ in range(20):
                ok, _ = run(f"curl -sf http://127.0.0.1:{port}/api/health >/dev/null && echo Y || echo N")
                if ok == "Y":
                    healthy = True
                    break
                print(".", end="", flush=True)
                import time as _t
                _t.sleep(3)
            print("")
            if not healthy:
                print("[❌] 健康检查 60 秒未通过,服务没有正常启动。诊断信息:")
                out, err = run(f"cd {r_dir} && docker compose ps -a 2>&1 | tail -6")
                print(out or err)
                out, err = run(f"cd {r_dir} && docker compose logs --tail 30 2>&1")
                print(out or err)
                print(f"[!] 请把上面的输出发给开发者,或手动检查: cd {r_dir} && docker compose ps && docker compose logs")
                sys.exit(1)
            print("=" * 54)
            print("  🎉 Docker 部署完成!")
            print(f"  网页后台: http://{host}:{port}")
            print(f"  访问令牌: {tok or '见服务器项目目录 .env 的 SPARK_TOKEN'}")
            print("  (数据在服务器项目目录 data/,重跑本脚本升级不丢)")
            print("=" * 54)
        ssh.close()
    except SystemExit:
        raise
    except Exception:
        print("[❌] 部署失败,完整错误如下(把这段发我即可定位):")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
