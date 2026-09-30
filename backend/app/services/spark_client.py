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
import threading
import time
from collections import defaultdict
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

import pyarrow.parquet as pq
from minio import Minio

from app.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_BUCKET_LAKE, MINIO_SECURE,
)
from app.services.media_store import media_store

logger = logging.getLogger(__name__)

# 全量标注帧的进程内 TTL 缓存（秒）：避免每次检索都重新下载整湖 Parquet
FRAMES_CACHE_TTL = 60.0
_frames_cache: Optional[List[Dict[str, Any]]] = None
_frames_cache_sig: Optional[tuple] = None
_frames_cache_at: float = 0.0
_frames_cache_lock = threading.Lock()


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

    def _list_parquet_objects(self) -> List[Tuple[str, str, str]]:
        """列出数据湖桶中全部标注 Parquet 对象 (name, etag, last_modified)"""
        try:
            if not self._minio.bucket_exists(MINIO_BUCKET_LAKE):
                return []
            return [
                (obj.object_name, obj.etag or "",
                 obj.last_modified.isoformat() if obj.last_modified else "")
                for obj in self._minio.list_objects(
                    MINIO_BUCKET_LAKE, prefix="annotations/", recursive=True)
                if obj.object_name.endswith(".parquet")
            ]
        except Exception as e:
            logger.warning(f"列出标注数据失败: {e}")
            return []

    def load_frames(self) -> List[Dict[str, Any]]:
        """加载数据湖全部标注帧（内存 TTL 缓存 + 按 (video_id, frame_index) 去重）。

        同一视频重复提交标注任务会在不同 parquet 中产生重复帧，保留最后一条
        （文件按任务时间先后追加，后写入的任务数据更新）。
        """
        global _frames_cache, _frames_cache_sig, _frames_cache_at
        objects = self._list_parquet_objects()
        if not objects:
            return []

        signature = tuple(sorted(
            (name, etag, last_modified) for name, etag, last_modified in objects
        ))
        with _frames_cache_lock:
            if (
                _frames_cache is not None
                and _frames_cache_sig == signature
                and time.time() - _frames_cache_at < FRAMES_CACHE_TTL
            ):
                return _frames_cache

        frames: List[Dict[str, Any]] = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                for name, _, _ in objects:
                    local = os.path.join(tmpdir, os.path.basename(name))
                    self._minio.fget_object(MINIO_BUCKET_LAKE, name, local)
                    table = pq.read_table(local)
                    frames.extend(table.to_pylist())
        except Exception as e:
            logger.warning(f"读取标注 Parquet 失败: {e}")
            return []

        # 去重：同一 (video_id, frame_index) 保留最后一条
        deduped: Dict[Tuple[str, Any], Dict[str, Any]] = {}
        for row in frames:
            deduped[(row.get("video_id", ""), row.get("frame_index"))] = row

        with _frames_cache_lock:
            _frames_cache = list(deduped.values())
            _frames_cache_sig = signature
            _frames_cache_at = time.time()
        logger.info(f"加载标注数据: {len(deduped)} 帧（{len(objects)} 个 Parquet）")
        return _frames_cache

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
        start_date, end_date = self._parse_time_range(time_range)
        video_dates = self._video_dates()

        tag_filter = set(global_tags or [])
        obj_filter = set(objects or [])

        # 读取全部标注帧（内存 TTL 缓存 + 去重）
        frames = self.load_frames()
        if not frames:
            logger.info("数据湖中暂无标注数据")
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

    def search_runs(
        self,
        objects: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        按检测目标 / 场景标签检索标注数据，返回「连续帧片段」分页列表。

        同一视频中连续命中（frame_index 递增 1）的帧合并为一条 run；
        每条 run 携带帧范围、目标/标签聚合统计与媒体 URL。
        过滤语义与 search() 一致：标签/目标取交集，两类条件 AND。
        """
        frames = self.load_frames()
        tag_filter = set(tags or [])
        obj_filter = set(objects or [])

        matched: List[Tuple[Dict[str, Any], list, list]] = []
        for row in frames:
            try:
                frame_tags = json.loads(row.get("global_tags") or "[]")
                frame_objs = json.loads(row.get("objects") or "[]")
            except (TypeError, ValueError):
                continue

            if tag_filter and not (tag_filter & set(frame_tags)):
                continue
            obj_classes = [o.get("class_name", "") for o in frame_objs if isinstance(o, dict)]
            if obj_filter and not (obj_filter & set(obj_classes)):
                continue
            matched.append((row, frame_tags, frame_objs))

        video_meta_map = media_store.get_video_meta_map()

        # 按 (video_id, frame_index) 排序后分组：连续帧合并为一条 run
        by_video: Dict[str, List[Tuple[Dict[str, Any], list, list]]] = defaultdict(list)
        for item in matched:
            by_video[item[0].get("video_id", "")].append(item)

        runs: List[Dict[str, Any]] = []
        for video_id, vframes in by_video.items():
            vframes.sort(key=lambda t: int(t[0].get("frame_index") or 0))
            current: List[Tuple[Dict[str, Any], list, list]] = []
            prev_idx: Optional[int] = None
            for item in vframes:
                idx = int(item[0].get("frame_index") or 0)
                if prev_idx is not None and idx != prev_idx + 1:
                    runs.append(_build_run(video_id, current, video_meta_map))
                    current = []
                current.append(item)
                prev_idx = idx
            if current:
                runs.append(_build_run(video_id, current, video_meta_map))

        # 排序：日期新的在前（未知日期排最后），同日期按视频/起始帧
        runs.sort(key=lambda r: (r["video_id"], r["start_frame"]))
        runs.sort(key=lambda r: (r["content_date"] or "", r["uploaded_date"] or ""), reverse=True)

        total = len(runs)
        start = (page - 1) * page_size
        return {
            "items": runs[start:start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_run_frames(
        self, video_id: str, start: int, end: int
    ) -> List[Dict[str, Any]]:
        """返回 run 范围内的逐帧明细（含 bbox），供前端逐帧导航与画框。

        仅依赖数据湖 Parquet，原始视频已删除时仍可返回。
        """
        frames = self.load_frames()
        result: List[Dict[str, Any]] = []
        for row in frames:
            if row.get("video_id") != video_id:
                continue
            idx = int(row.get("frame_index") or 0)
            if not (start <= idx <= end):
                continue
            try:
                tags = json.loads(row.get("global_tags") or "[]")
                objs = json.loads(row.get("objects") or "[]")
            except (TypeError, ValueError):
                tags, objs = [], []

            # 清洗 objects，保证与 DetectedObject schema 一致（bbox 为原始分辨率坐标）
            clean_objs = []
            for o in objs:
                if not isinstance(o, dict) or "class_name" not in o:
                    continue
                bbox = o.get("bbox")
                if not isinstance(bbox, dict):
                    continue
                clean_objs.append({
                    "bbox": {
                        "x": float(bbox.get("x") or 0),
                        "y": float(bbox.get("y") or 0),
                        "width": float(bbox.get("width") or 0),
                        "height": float(bbox.get("height") or 0),
                    },
                    "class_name": str(o["class_name"]),
                    "confidence": float(o.get("confidence") or 0),
                    "attributes": o.get("attributes"),
                })

            result.append({
                "video_id": video_id,
                "frame_index": idx,
                "timestamp_sec": float(row.get("timestamp_sec") or 0),
                "global_tags": tags,
                "objects": clean_objs,
                "blur_score": row.get("blur_score"),
                "quality_score": row.get("quality_score"),
            })
        result.sort(key=lambda f: f["frame_index"])
        return result

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


def _build_run(
    video_id: str,
    run: List[Tuple[Dict[str, Any], list, list]],
    video_meta_map: Dict[str, Any],
) -> Dict[str, Any]:
    """聚合一条连续帧片段为 AnnotationRun 结构"""
    start_frame = int(run[0][0].get("frame_index") or 0)
    end_frame = int(run[-1][0].get("frame_index") or 0)
    mid = run[len(run) // 2]
    mid_frame = int(mid[0].get("frame_index") or 0)

    obj_stats: Dict[str, Dict[str, float]] = {}
    tag_stats: Dict[str, int] = {}
    quality_scores: List[float] = []
    for row, frame_tags, frame_objs in run:
        for o in frame_objs:
            if not isinstance(o, dict):
                continue
            cls = o.get("class_name", "")
            if not cls:
                continue
            stat = obj_stats.setdefault(cls, {"count": 0, "max_conf": 0.0})
            stat["count"] += 1
            stat["max_conf"] = max(stat["max_conf"], float(o.get("confidence") or 0))
        for t in frame_tags:
            tag_stats[t] = tag_stats.get(t, 0) + 1
        qs = row.get("quality_score")
        if qs is not None:
            quality_scores.append(float(qs))

    meta = video_meta_map.get(video_id)
    return {
        "run_id": f"{video_id}-{start_frame}-{end_frame}",
        "video_id": video_id,
        "device_id": meta.device_id if meta else "",
        "camera_view": meta.camera_view if meta else "",
        "content_date": meta.content_date if meta else "",
        "uploaded_date": meta.uploaded_date if meta else "",
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": len(run),
        "start_sec": float(start_frame),
        "end_sec": float(end_frame),
        "objects": [
            {"class_name": cls, "count": int(s["count"]), "max_confidence": round(s["max_conf"], 3)}
            for cls, s in sorted(obj_stats.items(), key=lambda kv: -kv[1]["count"])
        ],
        "tags": [
            {"name": name, "count": count}
            for name, count in sorted(tag_stats.items(), key=lambda kv: -kv[1])
        ],
        "avg_quality": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0.0,
        "has_raw_video": meta is not None,
        "thumbnail_url": f"/api/annotations/frame/{video_id}/{mid_frame}",
        "clip_url": f"/api/annotations/clip/{video_id}?start_sec={start_frame}&end_sec={end_frame}",
    }
