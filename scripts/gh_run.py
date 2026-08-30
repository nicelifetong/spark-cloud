"""GitHub Actions 无服务器部署入口(第三种部署形态)。

续火本体跑在 Actions 上,零服务器零开机。数据(配置/好友/台账/Cookie)
加密后存进仓库 vault/data.enc,每轮跑完回写提交,循环持久化。

用法:
  python scripts/gh_run.py seal     # 本地:把 data/ 打包加密 -> vault/data.enc(推上仓库)
  python scripts/gh_run.py unseal   # 本地:把 vault/data.enc 解回 data/(改完再 seal)
  python scripts/gh_run.py run      # Actions:解密 -> 到点账号各跑一轮 -> 回写加密

密钥:环境变量 DATA_KEY(任意口令;本地 seal 与仓库 Secrets 必须一致)。
"""
from __future__ import annotations

import base64
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("SPARK_DATA") or (ROOT / "data"))
VAULT = Path(os.environ.get("SPARK_VAULT") or (ROOT / "vault" / "data.enc"))
# 北京 UTC+8,无夏令时,固定偏移即可(避免 Windows 缺 tzdata 依赖)
BJ = timezone(timedelta(hours=8))


def _fernet():
    key_pass = os.environ.get("DATA_KEY", "")
    if not key_pass:
        sys.exit("[x] 缺少环境变量 DATA_KEY(加密口令)")
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        sys.exit("[x] 缺少依赖:先 pip install cryptography")
    key = base64.urlsafe_b64encode(hashlib.sha256(key_pass.encode()).digest())
    return Fernet(key)


def seal() -> None:
    """data/ -> 加密 vault。"""
    if not DATA.exists():
        sys.exit(f"[x] 数据目录不存在: {DATA}")
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:gz") as t:
            t.add(DATA, arcname=".")
        VAULT.write_bytes(_fernet().encrypt(Path(tmp).read_bytes()))
    finally:
        os.unlink(tmp)
    print(f"[ok] 已加密 {DATA} -> {VAULT}")


def unseal() -> bool:
    """加密 vault -> data/。vault 不存在返回 False(首次部署)。"""
    if not VAULT.exists():
        print(f"[..] {VAULT} 不存在,跳过解密(首次部署)")
        return False
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    try:
        Path(tmp).write_bytes(_fernet().decrypt(VAULT.read_bytes()))
        DATA.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tmp, "r:gz") as t:
            try:
                t.extractall(DATA, filter="data")
            except TypeError:  # py<3.12 无 filter 参数
                t.extractall(DATA)
    finally:
        os.unlink(tmp)
    print(f"[ok] 已解密 {VAULT} -> {DATA}")
    return True


def _parse_hm(s: str):
    try:
        h, m = str(s).strip().split(":")
        return int(h), int(m)
    except Exception:
        return 9, 0


def run(dry: bool = False) -> int:
    """Actions 主循环:解密 -> 到点账号各跑一轮 -> 回写加密。"""
    unseal()
    os.environ.setdefault("SPARK_DATA", str(DATA))
    sys.path.insert(0, str(ROOT))

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    from keeper import accounts, runner

    now = datetime.now(BJ)
    now_hm = (now.hour, now.minute)
    print(f"[tick] 北京时间 {now:%Y-%m-%d %H:%M}(同日每账号最多执行一次)")

    act = 0
    for acc in accounts.list_accounts():
        aid = str(acc.get("id") or "")
        if not aid:
            continue
        try:
            cfg = accounts.load_config(aid)
        except Exception as e:
            print(f"[skip] {aid}: 读配置失败 {e}")
            continue
        if cfg.get("enabled") is False or acc.get("enabled") is False:
            print(f"[skip] {aid}: 账号停用")
            continue
        h, m = _parse_hm(cfg.get("schedule_time") or "09:00")
        if now_hm < (h, m):
            print(f"[skip] {aid}: 计划 {h:02d}:{m:02d} 未到")
            continue
        marker = DATA / "accounts" / aid / ".cloud_done"
        today = now.date().isoformat()
        if marker.exists() and marker.read_text(encoding="utf-8", errors="ignore").strip() == today:
            print(f"[skip] {aid}: 今天({today})已执行过,同日不重发")
            continue
        print(f"[run] {aid}(计划 {h:02d}:{m:02d})开始…")
        try:
            result = runner.run_once(aid, dry=dry)
            ok, bad = len(result.get("ok", [])), len(result.get("failed", []))
            note = result.get("note") or ""
            print(f"[done] {aid}: 成功 {ok} 失败 {bad} {note}")
            act += 1
            if not dry:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(today, encoding="utf-8")
        except Exception as e:
            print(f"[err] {aid}: {e}(下个拍子重试)")

    if act == 0:
        print("[tick] 本轮无账号需要执行")
    seal()  # 台账/运行状态无论如何回写,保证幂等
    print("[tick] 结束")
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "seal":
        seal()
    elif cmd == "unseal":
        unseal()
    elif cmd == "run":
        dry = "--dry" in sys.argv
        sys.exit(run(dry=dry))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
