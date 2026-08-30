#!/usr/bin/env bash
# Spark Cloud Docker 一键部署(Linux / macOS / NAS)
# 用法: bash deploy/docker-up.sh   (更新代码后再跑一次即可升级,data/ 数据不丢)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "======================================"
echo "  Spark Cloud - Linux 一键部署"
echo "======================================"

# ---------- 检查 docker ----------
if ! command -v docker &>/dev/null; then
  echo "[错误] 未检测到 Docker,请先安装:"
  echo "  https://docs.docker.com/get-docker/"
  echo "  (Ubuntu/Debian 快捷: curl -fsSL https://get.docker.com | bash)"
  exit 1
fi
if ! docker compose version &>/dev/null; then
  echo "[错误] 缺少 Docker Compose 插件(Docker 20.10+ 一般自带)。"
  echo "  Ubuntu/Debian 执行: sudo apt-get install -y docker-compose-plugin"
  exit 1
fi

# ---------- 首次生成 .env(随机访问令牌) ----------
if [ ! -f .env ]; then
  TOKEN=$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')
  cat > .env <<EOF
SPARK_TOKEN=$TOKEN
SPARK_PORT=8000
SPARK_HOST=0.0.0.0
SPARK_WEB_PORT=8000
TZ=Asia/Shanghai
EOF
  echo "[*] 已生成 .env,访问令牌: $TOKEN"
fi

# 读取自定义端口(默认 8000)
SPARK_WEB_PORT=$(grep '^SPARK_WEB_PORT=' .env | cut -d= -f2- | tr -d '\r\n' || true)
SPARK_WEB_PORT=${SPARK_WEB_PORT:-8000}

echo "[*] 构建镜像并启动(首次约需几分钟;已使用国内镜像源加速 apt/pip)…"
docker compose up -d --build

# ---------- 等待服务就绪(最多 90 秒) ----------
echo "[*] 等待服务就绪…"
probe() {  # curl 优先,没有就用 wget;都没有就跳过检测
  if command -v curl &>/dev/null; then
    curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$SPARK_WEB_PORT/api/health"
  elif command -v wget &>/dev/null; then
    wget -q -O /dev/null -T 2 "http://127.0.0.1:$SPARK_WEB_PORT/api/health"
  else
    return 0
  fi
}
for i in $(seq 1 90); do
  if probe; then ready=1; break; fi
  sleep 1
done
if [ "${ready:-0}" != "1" ]; then
  echo "[警告] 90 秒内健康检查未通过(可能只是机器慢)。"
  echo "  查看日志: docker compose logs -f"
else
  echo "[OK] 服务已就绪。"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
IP=${IP:-127.0.0.1}
TOKEN_VALUE=$(grep '^SPARK_TOKEN=' .env | cut -d= -f2- | tr -d '\r\n')
echo ""
echo "======================================================"
echo "  部署完成!"
echo ""
echo "  网页后台: http://$IP:$SPARK_WEB_PORT"
echo "  访问令牌: $TOKEN_VALUE   (保存在 .env 文件里)"
echo ""
echo "  下一步: 浏览器打开上面的网址 → 输入令牌 →"
echo "    「凭证」页扫码登录抖音 → 「好友」页同步+勾选 →"
echo "    「定时」页设置每天自动续火时间。"
echo ""
echo "  以后更新: 拉到新代码后再执行一次本脚本即可(data/ 不丢)。"
echo "  停止: docker compose down    日志: docker compose logs -f"
echo "======================================================"
