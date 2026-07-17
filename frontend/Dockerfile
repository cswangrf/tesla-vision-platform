# ============================================================
# Tesla Vision Platform - 前端 Dockerfile
# 多阶段构建：先编译 React 应用，再用 Nginx 托管
# ============================================================

# ---------- 阶段 1: 构建 ----------
FROM node:20-alpine AS builder

LABEL maintainer="dev@tesla-vision.local"

WORKDIR /app

# 配置 npm 镜像
RUN npm config set registry https://registry.npmmirror.com

# 安装依赖
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# 复制源代码
COPY public/ ./public/
COPY src/ ./src/
COPY index.html ./
COPY tsconfig.json tsconfig.node.json vite.config.ts ./

# 构建生产版本
RUN npm run build

# ---------- 阶段 2: 生产运行 ----------
FROM nginx:1.25-alpine

LABEL description="Tesla Vision Platform Frontend - Nginx + React SPA"

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制编译好的文件
COPY --from=builder /app/dist /usr/share/nginx/html

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/health || exit 1

EXPOSE 80
