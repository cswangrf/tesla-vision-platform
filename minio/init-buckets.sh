#!/bin/bash
# ============================================================
# Tesla Vision Platform - MinIO 初始化脚本
# 在 MinIO 启动后创建所需的存储桶
# ============================================================
set -e

# 等待 MinIO 启动
echo "等待 MinIO 服务启动..."
sleep 10

# MinIO 客户端配置
mc alias set local http://localhost:9000 minioadmin minioadmin

# 创建存储桶
echo "创建存储桶..."

# 原始视频
mc mb --ignore-existing local/tesla-raw-videos
echo "  ✓ tesla-raw-videos"

# 抽帧图片
mc mb --ignore-existing local/tesla-frames
echo "  ✓ tesla-frames"

# Parquet 数据湖
mc mb --ignore-existing local/tesla-lake
echo "  ✓ tesla-lake"

# 设置公共读取策略（用于前端直接访问视频/图片）
mc policy set download local/tesla-frames

echo "MinIO 初始化完成！"
