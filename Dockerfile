# Spark Cloud · 抖音自动续火花
FROM python:3.11-slim

# 构建参数:可自定义镜像源(国内加速,默认阿里云;也可用 mirrors.tuna.tsinghua.edu.cn / mirrors.ustc.edu.cn)
ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app
ENV TZ=Asia/Shanghai \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    SPARK_PORT=8000 \
    SPARK_HOST=0.0.0.0 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=$PIP_INDEX_URL

# 切换 apt 到国内镜像源,加速系统依赖安装
# (兼容 deb822 新格式 /etc/apt/sources.list.d/debian.sources 与 legacy /etc/apt/sources.list)
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    tzdata libnss3 libnspr4 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libzbar0 libglib2.0-0 xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# pip 单独一层:超时+重试,死连接不会挂死构建
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

# Chromium 下载单独一层:走 npmmirror 国内 CDN(官方 playwright 下载源在国外,
# 国内易断流且 playwright 下载器无超时,会卡死构建)+ 失败自动重试 3 次
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
RUN ok=0; for i in 1 2 3; do \
      echo "[browser] 第 $i 次尝试下载 Chromium…"; \
      if playwright install --with-deps chromium; then ok=1; break; else sleep 5; fi; \
    done; [ "$ok" = "1" ]

COPY . .

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status == 200 else 1)"

CMD ["python", "app.py"]
