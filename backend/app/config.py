"""
Tesla Vision Platform - 配置模块

配置优先级: 环境变量 > 默认值
可通过 .env 文件或 Docker 环境变量覆盖。
"""

import os
from pathlib import Path

# ============================================================
# MinIO 对象存储
# ============================================================
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_RAW = os.getenv("MINIO_BUCKET_RAW", "tesla-raw-videos")
MINIO_BUCKET_FRAMES = os.getenv("MINIO_BUCKET_FRAMES", "tesla-frames")
MINIO_BUCKET_LAKE = os.getenv("MINIO_BUCKET_LAKE", "tesla-lake")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# ============================================================
# Redis / Celery
# ============================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# ============================================================
# 模型推理服务
# ============================================================
CLIP_SERVICE_URL = os.getenv("CLIP_SERVICE", "http://chinese-clip:8500")
LAM_SERVICE_URL = os.getenv("LAM_SERVICE", "http://locate-anything:8501")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# ============================================================
# Spark
# ============================================================
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")

# ============================================================
# 视频处理
# ============================================================
FRAME_EXTRACT_INTERVAL = int(os.getenv("FRAME_EXTRACT_INTERVAL", "30"))  # 每30帧抽1帧 (~1fps@30fps)
VIDEO_CLIP_DURATION_SEC = int(os.getenv("VIDEO_CLIP_DURATION_SEC", "60"))  # 1分钟片段

# 场景候选词（Chinese-CLIP 零样本分类）
SCENE_CANDIDATES = [
    "高速公路", "城市街道", "隧道", "雨天", "夜间", "停车场",
    "十字路口", "拥堵路段", "施工路段", "乡村道路", "晴天", "白天"
]

# 目标检测提示词
OBJECT_PROMPTS = ["车辆", "行人", "交通标志", "红绿灯", "障碍物", "自行车", "摩托车"]

# ============================================================
# 服务配置
# ============================================================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ============================================================
# 路径
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
