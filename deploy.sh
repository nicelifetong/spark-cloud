#!/data/data/com.termux/files/usr/bin/bash
# spark-cloud · 安卓一键部署(Termux)
# 流程:装依赖 → 开后台扫码+配置(好友/时间/推送)→ 建仓上传 → 完成
# 用法:bash deploy.sh [仓库名](默认 spark-cloud)
set -e
say(){ printf '\n\033[1;36m===== %s =====\033[0m\n' "$*"; }

[ -f scripts/gh_run.py ] || { echo "[x] 请先进入 spark-cloud 仓库目录再运行:bash deploy.sh"; exit 1; }

say "1/5 安装依赖(已装自动跳过)"
command -v python >/dev/null 2>&1 || pkg install -y python
command -v git   >/dev/null 2>&1 || pkg install -y git
command -v gh    >/dev/null 2>&1 || pkg install -y gh

say "2/5 抖音扫码 + 后台配置(好友/时间/推送都在这里配)"
echo "凭证页即将启动,手机浏览器打开屏幕上的地址 → 「凭证页」→ 抖音扫码。"
python app.py &
APP_PID=$!
sleep 4
command -v termux-open >/dev/null 2>&1 && termux-open "http://127.0.0.1:8000" 2>/dev/null || true
read -r -p "请在后台完成:扫码登录 → 定时页选好友/设时间 → 设置-通知设置绑定推送。全部配好后按回车继续… " _
kill "$APP_PID" 2>/dev/null || true

say "3/5 登录 GitHub(浏览器授权)"
gh auth status >/dev/null 2>&1 || gh auth login -w -p https
GHUSER=$(gh api user -q .login)
echo "已登录:$GHUSER"

REPO="${1:-spark-cloud}"
say "4/5 建私有仓库 $GHUSER/$REPO 并上传(代码+配置一次到位)"
KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
DATA_KEY="$KEY" python scripts/gh_run.py seal
printf '%s' "$KEY" > .seal_key
chmod 600 .seal_key
git remote remove origin 2>/dev/null || true
gh repo view "$GHUSER/$REPO" >/dev/null 2>&1 || gh repo create "$REPO" --private
git remote add origin "https://github.com/$GHUSER/$REPO.git"
git add vault/data.enc
git commit -m "chore: 初始加密包(新口令)" || true
git push -u origin main

say "5/5 写入 Secret(DATA_KEY)"
gh secret set DATA_KEY -R "$GHUSER/$REPO" --body "$KEY"

say "完成 ✅"
echo "仓库: https://github.com/$GHUSER/$REPO"
echo "打开 Actions 页确认 streak 在跑(每小时 :13 一拍,到点自动发)。"
echo "以后改配置:python app.py 改完 → bash sync.sh"
