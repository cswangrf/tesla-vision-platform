# ============================================================
# Tesla Vision Platform - Annotation Worker Dockerfile
# GPU 推理服务 (Chinese-CLIP + LocateAnything-3B)
# ============================================================
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

LABEL maintainer="dev@tesla-vision.local"
LABEL description="Tesla Vision Platform - Annotation Inference Worker"

WORKDIR /app

# 配置 apt 镜像源（阿里云）
RUN sed -i 's|http://.*.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || \
    sed -i 's|archive.ubuntu.com|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    build-essential \
    python3-dev \
    patch \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 配置 pip 镜像源为清华（并允许额外从官方源获取 wheel）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Python 依赖（启用缓存挂载 + prefer-binary）
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefer-binary \
    --extra-index-url https://pypi.org/simple \
    -r requirements.txt

# 复制应用代码
COPY server.py .
COPY chinese_clip.py .
COPY locate_anything.py .

# 创建模型缓存目录
RUN mkdir -p /models /root/.cache/huggingface

EXPOSE 8500 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8500}/health').read()" || exit 1

CMD ["python", "server.py", "--port", "8500", "--model", "chinese-clip"]