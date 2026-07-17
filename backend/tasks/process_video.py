"""
Tesla Vision Platform - 视频处理 Celery 任务

负责视频抽帧、调用标注引擎生成标注、保存结果。
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import List, Dict, Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.tasks.celery_app import celery_app
from app.utils.video_utils import extract_frames, get_video_info, compute_blur_score
from app.services.annotation_engine import AnnotationClient
from app.config import (
    CLIP_SERVICE_URL, LAM_SERVICE_URL,
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_BUCKET_LAKE,
)

logger = logging.getLogger(__name__)

# 任务状态存储（引用 tasks.py 中的共享存储）
try:
    from app.routers.tasks import _task_store, TaskStatus
except ImportError:
    _task_store = {}


def _update_task_status(task_id: str, status: str, progress: float = None, error: str = None):
    """更新任务状态"""
    task = _task_store.get(task_id)
    if task:
        task.status = status
        if progress is not None:
            task.progress = progress
        if error:
            task.error = error
        task.updated_at = datetime.now()


@celery_app.task(bind=True, name="process_video")
def process_video_task(self, task_id: str, video_ids: List[str]):
    """
    视频处理任务：
    1. 从 MinIO 下载视频
    2. 按 1fps 抽帧
    3. 并发调用 Chinese-CLIP + LocateAnything 标注
    4. 保存结果为 Parquet
    5. 计算质量分数
    """
    _update_task_status(task_id, "processing", 0.0)

    try:
        annotation_client = AnnotationClient(
            clip_url=CLIP_SERVICE_URL,
            lam_url=LAM_SERVICE_URL,
        )

        total_videos = len(video_ids)
        all_annotations: List[Dict[str, Any]] = []

        for i, video_id in enumerate(video_ids):
            logger.info(f"处理视频 {video_id} ({i+1}/{total_videos})")

            # 进度更新
            base_progress = (i / total_videos) * 0.8  # 80% 用于抽帧+标注
            _update_task_status(task_id, "processing", base_progress)

            # 在临时目录中处理
            with tempfile.TemporaryDirectory() as tmpdir:
                # TODO: 从 MinIO 下载视频
                # 目前使用模拟数据演示流程
                video_path = os.path.join(tmpdir, f"{video_id}.mp4")

                # 抽帧
                frames_dir = os.path.join(tmpdir, "frames")
                frame_paths = extract_frames(video_path, frames_dir, fps=1.0)

                if not frame_paths:
                    logger.warning(f"视频 {video_id} 没有抽取到帧")
                    continue

                # 逐帧标注
                for frame_idx, frame_path in enumerate(frame_paths):
                    with open(frame_path, "rb") as f:
                        image_bytes = f.read()

                    # 调用标注引擎（中国-CLIP + LocateAnything）
                    try:
                        annotation = annotation_client.annotate_frame_sync(image_bytes)
                    except Exception as e:
                        logger.warning(f"帧 {frame_idx} 标注失败: {e}")
                        annotation = {
                            "embedding": [],
                            "global_tags": [],
                            "objects": [],
                        }

                    # 计算模糊分数
                    blur_score = compute_blur_score(frame_path)

                    # 构建帧标注记录
                    frame_record = {
                        "video_id": video_id,
                        "frame_index": frame_idx,
                        "timestamp_sec": float(frame_idx),  # 1fps, 所以 frame_index = 秒数
                        "global_embedding": annotation.get("embedding", []),
                        "global_tags": annotation.get("global_tags", []),
                        "objects": annotation.get("objects", []),
                        "blur_score": blur_score,
                        "quality_score": _compute_quality(annotation, blur_score),
                    }
                    all_annotations.append(frame_record)

                # 子进度
                sub_progress = base_progress + (0.8 / total_videos)
                _update_task_status(task_id, "processing", sub_progress)

        # 保存为 Parquet
        _update_task_status(task_id, "processing", 0.85)
        parquet_path = _save_to_parquet(all_annotations, task_id)
        logger.info(f"标注结果已保存: {parquet_path}")

        # 生成摘要
        summary = _generate_summary(all_annotations)

        _update_task_status(task_id, "completed", 1.0)

        return {
            "task_id": task_id,
            "total_frames": len(all_annotations),
            "parquet_path": parquet_path,
            "summary": summary,
        }

    except Exception as e:
        logger.error(f"视频处理任务失败: {e}", exc_info=True)
        _update_task_status(task_id, "failed", error=str(e))
        raise


def _compute_quality(annotation: dict, blur_score: float) -> float:
    """
    计算帧质量分数 (0-100)。

    考虑因素：
    - 模糊分数
    - 检测到的目标数量
    - 标签丰富度
    """
    score = 50.0  # 基础分

    # 清晰度 (max 20)
    if blur_score > 500:
        score += 20
    elif blur_score > 100:
        score += 10
    elif blur_score > 50:
        score += 5

    # 目标数量 (max 20)
    obj_count = len(annotation.get("objects", []))
    score += min(obj_count * 4, 20)

    # 标签丰富度 (max 10)
    tag_count = len(annotation.get("global_tags", []))
    score += min(tag_count * 3, 10)

    return min(score, 100.0)


def _save_to_parquet(annotations: List[Dict[str, Any]], task_id: str) -> str:
    """
    将标注结果保存为 Parquet 文件。

    Args:
        annotations: 标注记录列表
        task_id: 任务 ID

    Returns:
        保存的 Parquet 文件路径
    """
    output_dir = os.path.join("/app/data/annotations", task_id)
    os.makedirs(output_dir, exist_ok=True)

    parquet_path = os.path.join(output_dir, "frame_annotations.parquet")

    # 构建 PyArrow Table
    if not annotations:
        return parquet_path

    # 转换 objects 为 JSON 字符串（Parquet 不支持嵌套结构）
    records = []
    for ann in annotations:
        record = dict(ann)
        record["objects"] = json.dumps(record.get("objects", []), ensure_ascii=False)
        record["global_tags"] = json.dumps(record.get("global_tags", []), ensure_ascii=False)
        records.append(record)

    # 定义 schema
    schema = pa.schema([
        ("video_id", pa.string()),
        ("frame_index", pa.int32()),
        ("timestamp_sec", pa.float64()),
        ("global_embedding", pa.list_(pa.float32())),
        ("global_tags", pa.string()),
        ("objects", pa.string()),
        ("blur_score", pa.float64()),
        ("quality_score", pa.float64()),
    ])

    table = pa.Table.from_pylist(records, schema=schema)
    pq.write_table(table, parquet_path, compression="snappy")

    logger.info(f"保存 {len(records)} 条标注到 {parquet_path}")
    return parquet_path


def _generate_summary(annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    生成标注数据摘要统计。
    """
    if not annotations:
        return {"total_frames": 0}

    total_frames = len(annotations)

    # 统计标签频率
    tag_counts: Dict[str, int] = {}
    obj_counts: Dict[str, int] = {}
    quality_scores = []

    for ann in annotations:
        for tag in ann.get("global_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for obj in ann.get("objects", []):
            obj_name = obj.get("class_name", "unknown")
            obj_counts[obj_name] = obj_counts.get(obj_name, 0) + 1
        qs = ann.get("quality_score", 0)
        if qs:
            quality_scores.append(qs)

    # 获取主要场景（Top-5 标签）
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_frames": total_frames,
        "dominant_scenes": [t[0] for t in top_tags],
        "object_counts": obj_counts,
        "average_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
    }
