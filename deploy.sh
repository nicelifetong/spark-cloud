#!/data/data/com.termux/files/usr/bin/bash
# spark-cloud · 安卓一键部署(Termux)
# 前提:已在 Termux 里 clone 本仓库并 cd 进目录
# 用法:bash deploy.sh [仓库名](默认 spark-cloud)
set -e
say(){ printf '\n\033[1;36m===== %s =====\033[0m\n' "$*"; }

[ -f scripts/gh_run.py ] || { echo "[x] 请先进入 spark-cloud 仓库目录再运行:bash deploy.sh"; exit 1; }

say "1/7 安装依赖(已装自动跳过)"
command -v python >/dev/null 2>&1 || pkg install -y python
command -v git   >/dev/null 2>&1 || pkg install -y git
command -v gh    >/dev/null 2>&1 || pkg install -y gh

say "2/7 登录 GitHub(会弹浏览器授权)"
gh auth status >/dev/null 2>&1 || gh auth login -w -p https
GHUSER=$(gh api user -q .login)
echo "已登录:$GHUSER"

REPO="${1:-spark-cloud}"
say "3/7 创建私有仓库 $GHUSER/$REPO 并推送代码"
git remote remove origin 2>/dev/null || true
gh repo view "$GHUSER/$REPO" >/dev/null 2>&1 || gh repo create "$REPO" --private
git remote add origin "https://github.com/$GHUSER/$REPO.git"
git push -u origin main

say "4/7 抖音扫码登录(凭证页)"
echo "接下来凭证页会启动,手机浏览器打开下面提示的地址 → 凭证页 → 抖音扫码。"
echo "扫码成功后回到 Termux 按回车继续。"
python app.py &
APP_PID=$!
sleep 4
echo ">>> 浏览器打开 app.py 输出的地址(形如 http://127.0.0.1:8000/?token=xxx)"
command -v termux-open >/dev/null 2>&1 && termux-open "http://127.0.0.1:8000" 2>/dev/null || true
read -r -p "扫码完成并看到登录成功后,按回车继续… " _
kill "$APP_PID" 2>/dev/null || true

say "5/7 生成本仓库专属口令 + 加密封包"
KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
DATA_KEY="$KEY" python scripts/gh_run.py seal
printf '%s' "$KEY" > .seal_key
chmod 600 .seal_key
git add vault/data.enc
git commit -m "chore: 初始加密包(新口令)" || true
git push

say "6/7 写入 GitHub Secret(DATA_KEY)"
gh secret set DATA_KEY -R "$GHUSER/$REPO" --body "$KEY"

say "7/7 完成 ✅"
echo "仓库: https://github.com/$GHUSER/$REPO"
echo "打开 Actions 页确认 streak 在跑(每小时 :13 一拍,到点自动发)。"
echo "口令已存本机 .seal_key,别删——以后重新 seal 还要用。"
