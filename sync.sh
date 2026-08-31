#!/data/data/com.termux/files/usr/bin/bash
# spark-cloud · 手机改完配置后同步到 GitHub Actions
# 用法:网页里改好时间/好友后  bash sync.sh
set -e
cd "$(dirname "$0")"
[ -f .seal_key ] || { echo "[x] 找不到 .seal_key,请先跑过 deploy.sh"; exit 1; }
KEY=$(cat .seal_key)
git pull --rebase origin main
DATA_KEY="$KEY" python scripts/gh_run.py seal
git add vault/data.enc
git commit -m "sync: 同步最新配置到云端" || true
git push
echo "✅ 已同步,云端下一拍(每小时 :13)就会用新配置"
