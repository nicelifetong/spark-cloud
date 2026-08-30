#!/usr/bin/env bash
# Spark Cloud 一键部署脚本(Ubuntu/Debian 等 apt 系;支持 dnf/yum 基础安装)
set -euo pipefail

echo "======================================================"
echo "  🔥 Spark Cloud · 抖音自动续火花 一键部署"
echo "======================================================"

if [ "$(id -u)" -ne 0 ]; then
  echo "[错误] 请以 root 运行: sudo bash deploy/deploy.sh"
  exit 1
fi

SERVICE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SERVICE_DIR/.venv"
UNIT_SRC="$SERVICE_DIR/deploy/spark-cloud.service"
UNIT_DST="/etc/systemd/system/spark-cloud.service"

echo "==> 1. 安装系统依赖"
if command -v apt-get &>/dev/null; then
  apt-get update -y
  # 核心三件套必须装成功(失败就终止,不让错误静默传递)
  apt-get install -y python3 python3-venv python3-pip
  # 其余库:先试 24.04+ 的 t64 新包名,失败回落旧包名(libasound2 在新系统改名)
  apt-get install -y xvfb libnss3 libnspr4 libasound2t64 libatk1.0-0t64 \
    libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libzbar0 libglib2.0-0t64 2>/dev/null \
  || apt-get install -y xvfb libnss3 libnspr4 libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
    libzbar0 libglib2.0-0 2>/dev/null || true
elif command -v dnf &>/dev/null; then
  dnf install -y python3 python3-pip || true
elif command -v yum &>/dev/null; then
  yum install -y python3 python3-pip || true
fi

echo "==> 2. 创建虚拟环境并安装依赖"
# 无论上次是否残留半坏的 .venv,都重建(数据在 data/,不受影响)
rm -rf "$VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$SERVICE_DIR/requirements.txt" -q

echo "==> 3. 安装 Playwright Chromium"
# Chromium 走 npmmirror 国内 CDN(官方源国外易断流,下载器无超时会卡死)+ 重试 3 次
export PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright"
ok=0; for i in 1 2 3; do
  echo "[browser] 第 $i 次尝试下载 Chromium…"
  if "$VENV/bin/playwright" install --with-deps chromium; then ok=1; break; else sleep 5; fi
done
[ "$ok" = "1" ] || { echo "[❌] Chromium 下载失败(已重试 3 次)"; exit 1; }

echo "==> 4. 配置访问令牌"
if [ ! -f "$SERVICE_DIR/.env" ]; then
  TOKEN="$(head -c 24 /dev/urandom | sha256sum | head -c 24)"
  cat > "$SERVICE_DIR/.env" <<EOF
SPARK_TOKEN=$TOKEN
SPARK_PORT=8000
SPARK_HOST=0.0.0.0
TZ=Asia/Shanghai
EOF
  echo "    已生成令牌: $TOKEN"
fi

# 读取应用端口(默认 8000)
APP_PORT="$(grep '^SPARK_PORT=' "$SERVICE_DIR/.env" | cut -d= -f2- | tr -d '\r\n' || true)"
APP_PORT="${APP_PORT:-8000}"

echo "==> 5. 注册 systemd 开机自启"
systemctl stop spark-cloud 2>/dev/null || true
pkill -9 -f "python.*app.py" 2>/dev/null || true
fuser -k -9 "${APP_PORT}/tcp" 2>/dev/null || true
sed "s|__DIR__|$SERVICE_DIR|g; s|__VENV__|$VENV|g" "$UNIT_SRC" > "$UNIT_DST"
systemctl daemon-reload
systemctl enable --now spark-cloud
systemctl restart spark-cloud
sleep 2

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
TOKEN_VALUE="$(grep '^SPARK_TOKEN=' "$SERVICE_DIR/.env" | cut -d= -f2- | tr -d '\r\n')"
echo ""
echo "======================================================"
echo "  🎉 部署完成!"
echo "  Web 后台: http://$IP:$APP_PORT"
echo "  访问令牌: ${TOKEN_VALUE:-未设置}"
echo "======================================================"
echo "下一步:"
echo "  1. 服务器安全组放行 $APP_PORT 端口(TCP);"
echo "  2. 电脑上运行 scripts/1.提取登录态.bat 扫码;"
echo "  3. 网页后台「凭证」页上传 state.json 或直接网页扫码;"
echo "  4. 「好友」页同步并勾选,「定时」页设置时间,开始自动续火花!"
echo "======================================================"
