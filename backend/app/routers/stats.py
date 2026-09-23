"""
Tesla Vision Platform - 数据看板统计路由
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter
from minio import Minio

from app.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_SECURE,
)
from app.services.spark_client import SparkQueryClient
from app.routers.tasks import _task_store

logger = logging.getLogger(__name__)

router = APIRouter()

_minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


@router.get("/summary")
async def stats_summary() -> Dict[str, Any]:
    """
    看板汇总数据：
    - videos: 原始视频概况（文件数、片段数、设备列表、总大小）
    - annotations: 标注统计（帧数、目标分布、场景标签分布、已标注视频）
    - tasks: 任务数量（当前 API 进程内提交的任务）
    """
    # ---- 视频概况（MinIO raw 桶） ----
    total_files = 0
    total_size = 0
    clips = set()
    devices = set()
    try:
        if _minio_client.bucket_exists(MINIO_BUCKET_RAW):
            for obj in _minio_client.list_objects(
                MINIO_BUCKET_RAW, prefix="raw/", recursive=True
            ):
                parts = obj.object_name.replace("raw/", "").split("/")
                if len(parts) < 3:
                    continue
                total_files += 1
                total_size += obj.size
                clips.add(f"{parts[0]}|{parts[1]}")
                devices.add(parts[0])
    except Exception as e:
        logger.warning(f"统计视频概况失败: {e}")

    # ---- 标注统计（数据湖，无过滤条件即全量统计） ----
    annotation_client = SparkQueryClient()
    search_results = await annotation_client.search()
    annotation_stats = search_results[0] if search_results else {}

    # ---- 任务概况 ----
    tasks = list(_task_store.values())
    task_counts: Dict[str, int] = {}
    for t in tasks:
        key = t.status.value if hasattr(t.status, "value") else str(t.status)
        task_counts[key] = task_counts.get(key, 0) + 1

    return {
        "videos": {
            "total_files": total_files,
            "clips": len(clips),
            "devices": sorted(devices),
            "total_size_bytes": total_size,
        },
        "annotations": annotation_stats,
        "tasks": {"total": len(tasks), **task_counts},
    }
