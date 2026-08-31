#!/data/data/com.termux/files/usr/bin/bash
# spark-cloud · 上传到 GitHub Actions(在后台配置好之后运行)
# 用法:bash deploy.sh [仓库名](默认 spark-cloud)
set -e
say(){ printf '\n\033[1;36m===== %s =====\033[0m\n' "$*"; }

[ -f scripts/gh_run.py ] || { echo "[x] 请先进入 spark-cloud 仓库目录"; exit 1; }
[ -f data/state.json ] || { echo "[x] 还没登录抖音:先 python app.py 打开后台扫码并配置好,再跑本命令"; exit 1; }

say "1/4 登录 GitHub(浏览器授权)"
command -v gh >/dev/null 2>&1 || pkg install -y gh
gh auth status >/dev/null 2>&1 || gh auth login -w -p https
GHUSER=$(gh api user -q .login)
echo "已登录:$GHUSER"

REPO="${1:-spark-cloud}"
say "2/4 加密封包(生成仓库专属口令)"
KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
DATA_KEY="$KEY" python scripts/gh_run.py seal
printf '%s' "$KEY" > .seal_key
chmod 600 .seal_key

say "3/4 建私有仓库 $GHUSER/$REPO 并上传(代码+配置一次到位)"
git remote remove origin 2>/dev/null || true
gh repo view "$GHUSER/$REPO" >/dev/null 2>&1 || gh repo create "$REPO" --private
git remote add origin "https://github.com/$GHUSER/$REPO.git"
git add vault/data.enc
git commit -m "chore: 初始加密包(新口令)" || true
git push -u origin main

say "4/4 写入 Secret(DATA_KEY)"
gh secret set DATA_KEY -R "$GHUSER/$REPO" --body "$KEY"

say "完成 ✅"
echo "仓库: https://github.com/$GHUSER/$REPO"
echo "打开 Actions 页确认 streak 在跑(每小时 :13 一拍,到点自动发)。"
echo "以后改配置:python app.py 改完 → bash sync.sh"
