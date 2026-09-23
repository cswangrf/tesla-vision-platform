"""
Tesla Vision Platform - 标注数据检索客户端

当前实现：直接读取 MinIO 数据湖桶中的 frame_annotations Parquet 文件，
在 API 服务内完成筛选与聚合（Spark 集群集成留待后续，接口签名保持一致）。
"""

import json
import logging
import os
import re
import tempfile
from datetime import date
from typing import List, Dict, Any, Optional

import pyarrow.parquet as pq
from minio import Minio

from app.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_BUCKET_LAKE, MINIO_SECURE,
)

logger = logging.getLogger(__name__)


class SparkQueryClient:
    """
    标注数据查询客户端，用于检索 frame_annotations 数据。

    数据来源：celery worker 处理完视频后把标注 Parquet 上传到
    MinIO 数据湖桶（annotations/ 前缀），本客户端下载后在内存中筛选聚合。
    """

    def __init__(self):
        self._minio = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _list_parquets(self) -> List[str]:
        """列出数据湖桶中全部标注 Parquet 对象名"""
        try:
            if not self._minio.bucket_exists(MINIO_BUCKET_LAKE):
                return []
            return [
                obj.object_name
                for obj in self._minio.list_objects(
                    MINIO_BUCKET_LAKE, prefix="annotations/", recursive=True)
                if obj.object_name.endswith(".parquet")
            ]
        except Exception as e:
            logger.warning(f"列出标注数据失败: {e}")
            return []

    def _video_dates(self) -> Dict[str, tuple]:
        """video_id (etag 前8位) -> (内容时间戳日期, 上传日期)

        内容时间戳来自文件名（行车记录仪录像时间），上传日期来自 MinIO 对象元数据。
        时间过滤时两者任一命中即算匹配（"今天"既可能指录像日期也可能指上传日期）。
        """
        mapping: Dict[str, tuple] = {}
        try:
            for obj in self._minio.list_objects(MINIO_BUCKET_RAW, prefix="raw/", recursive=True):
                if not obj.etag:
                    continue
                m = re.search(r'(\d{4}-\d{2}-\d{2})', obj.object_name)
                content_date = m.group(1) if m else ""
                upload_date = (
                    obj.last_modified.date().isoformat() if obj.last_modified else ""
                )
                mapping[obj.etag[:8]] = (content_date, upload_date)
        except Exception as e:
            logger.warning(f"读取视频元数据失败: {e}")
        return mapping

    def _parse_time_range(self, time_range: Optional[str]):
        """解析时间范围字符串，返回 (start_date, end_date)，无范围时返回 (None, None)。

        支持: 'YYYY-MM-DD'、'YYYY-MM-DD 至 YYYY-MM-DD'、'today'/'今天'
        """
        if not time_range:
            return None, None
        if 'today' in time_range.lower() or '今天' in time_range:
            d = date.today().isoformat()
            return d, d
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', time_range)
        if not dates:
            return None, None
        return dates[0], (dates[1] if len(dates) > 1 else dates[0])

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def search(
        self,
        global_tags: Optional[List[str]] = None,
        objects: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        按语义标签 / 检测目标 / 时间范围检索标注数据，返回分布统计。

        Returns:
            最多一个结果元素，包含:
            - total_frames / matched_frames: 总帧数与匹配帧数
            - object_distribution: 检测目标类别 -> 出现次数
            - tag_distribution: 全局语义标签 -> 出现帧数
            - matched_videos: 每个匹配视频的帧数与时间戳
            无匹配或数据湖为空时返回空列表
        """
        parquet_names = self._list_parquets()
        if not parquet_names:
            logger.info("数据湖中暂无标注数据")
            return []

        start_date, end_date = self._parse_time_range(time_range)
        video_dates = self._video_dates()

        tag_filter = set(global_tags or [])
        obj_filter = set(objects or [])

        # 读取全部标注帧
        frames: List[Dict[str, Any]] = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                for name in parquet_names:
                    local = os.path.join(tmpdir, os.path.basename(name))
                    self._minio.fget_object(MINIO_BUCKET_LAKE, name, local)
                    table = pq.read_table(local)
                    frames.extend(table.to_pylist())
        except Exception as e:
            logger.warning(f"读取标注 Parquet 失败: {e}")
            return []

        logger.info(
            f"检索标注数据: 共 {len(frames)} 帧, "
            f"tags={global_tags}, objects={objects}, time_range={time_range}"
        )

        # 筛选 + 聚合
        obj_dist: Dict[str, int] = {}
        tag_dist: Dict[str, int] = {}
        per_video: Dict[str, Dict[str, Any]] = {}

        for row in frames:
            try:
                frame_tags = json.loads(row.get("global_tags") or "[]")
                frame_objs = json.loads(row.get("objects") or "[]")
            except (TypeError, ValueError):
                continue

            video_id = row.get("video_id", "")

            # 时间范围过滤（内容时间戳日期或上传日期任一命中）
            if start_date:
                vd = video_dates.get(video_id)
                content_ok = bool(vd and vd[0] and start_date <= vd[0] <= end_date)
                upload_ok = bool(vd and vd[1] and start_date <= vd[1] <= end_date)
                if not (content_ok or upload_ok):
                    continue

            # 标签过滤（取交集）
            if tag_filter and not (tag_filter & set(frame_tags)):
                continue

            # 目标过滤
            obj_classes = [o.get("class_name", "") for o in frame_objs if isinstance(o, dict)]
            if obj_filter and not (obj_filter & set(obj_classes)):
                continue

            # 聚合统计
            for tag in frame_tags:
                tag_dist[tag] = tag_dist.get(tag, 0) + 1
            for cls in obj_classes:
                obj_dist[cls] = obj_dist.get(cls, 0) + 1

            if video_id not in per_video:
                vd = video_dates.get(video_id, ("", ""))
                per_video[video_id] = {
                    "video_id": video_id,
                    "date": vd[0],
                    "uploaded_date": vd[1],
                    "matched_frames": 0,
                }
            per_video[video_id]["matched_frames"] += 1

        matched_frames = sum(v["matched_frames"] for v in per_video.values())
        if matched_frames == 0:
            return []

        matched_videos = sorted(
            per_video.values(), key=lambda v: v["matched_frames"], reverse=True
        )[:limit]

        return [{
            "total_frames": len(frames),
            "matched_frames": matched_frames,
            "time_range": f"{start_date} 至 {end_date}" if start_date else None,
            "object_distribution": dict(sorted(obj_dist.items(), key=lambda x: -x[1])),
            "tag_distribution": dict(sorted(tag_dist.items(), key=lambda x: -x[1])),
            "matched_videos": matched_videos,
        }]

    async def query_by_sql(self, sql: str) -> List[Dict[str, Any]]:
        """
        直接执行 SQL 查询（预留接口，当前未接入 Spark）。
        """
        logger.info(f"执行 SQL（未接入 Spark，返回空）: {sql}")
        return []

    async def get_video_stats(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        获取视频的聚合统计信息（预留接口，当前未接入 Spark）。
        """
        return None
