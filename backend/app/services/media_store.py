"""
Tesla Vision Platform - 标注媒体按需生成服务

按需从原始视频（tesla-raw-videos 桶）抽帧 / 切片段，结果缓存在
tesla-frames 桶（内容寻址：video_id 由 MinIO 对象 etag 派生，永不过期）。

视频元数据（设备、视角、日期）与 ffprobe 探测结果在进程内 TTL 缓存，
避免每次请求全桶列举 / 重复探测。
"""

import asyncio
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from minio import Minio
from minio.error import S3Error

from app.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_BUCKET_FRAMES, MINIO_SECURE,
)

logger = logging.getLogger(__name__)

# 进程内 TTL 缓存时长（秒）
META_CACHE_TTL = 60.0
PROBE_CACHE_TTL = 600.0

# 切片 / 抽帧的 ffmpeg 超时（与 nginx read_timeout 600s 对齐）
FFMPEG_TIMEOUT_SEC = 600


class MediaNotFound(Exception):
    """原始视频不存在 / 帧超出视频时长 / 切片生成失败（router 转 404）"""


@dataclass
class VideoMeta:
    """原始视频对象元数据（video_id = MinIO etag 前 8 位）"""
    video_id: str
    object_name: str
    device_id: str = ""
    timestamp: str = ""
    camera_view: str = ""
    content_date: str = ""    # 行车记录仪录像日期（对象 key 中解析）
    uploaded_date: str = ""   # MinIO 上传日期
    size_bytes: int = 0
    fps: float = 0.0          # ffprobe 懒探测
    width: int = 0
    height: int = 0


def _parse_fps(value: Optional[str]) -> float:
    """解析 ffprobe r_frame_rate，支持 '30000/1001' 分数格式；失败回退 30.0"""
    if not value:
        return 30.0
    try:
        if "/" in value:
            num, den = value.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else 30.0
        return float(value)
    except ValueError:
        return 30.0


def _seek_sec(frame_index: float, fps: float) -> float:
    """帧序号 → 源视频时间（秒）。

    抽帧是 cv2 按 int(fps/1) 帧间隔取帧：第 k 帧 = 源视频第 k*int(fps) 帧，
    位于 k*int(fps)/fps 秒。非整数帧率（如 29.97）下朴素 -ss k 会漂移，
    导致抽出的帧与标注时的帧不一致（bbox 无法对齐）。
    """
    interval = int(max(fps, 1.0))
    return frame_index * interval / max(fps, 1.0)


class MediaStore:
    """按需生成标注帧图 / 视频切片，MinIO 持久缓存 + 进程内 TTL 缓存。"""

    def __init__(self):
        self._minio = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        # 原始桶元数据映射缓存
        self._meta_map: Optional[Dict[str, VideoMeta]] = None
        self._meta_at = 0.0
        # ffprobe 探测结果缓存（key = object_name）
        self._probe_cache: Dict[str, Tuple[float, int, int]] = {}
        self._probe_at: Dict[str, float] = {}
        self._lock = threading.Lock()
        # 帧缓存桶懒初始化
        self._bucket_ready = False
        # 每缓存 key 一个 asyncio.Lock，防并发重复生成（仅限事件循环线程访问）
        self._gen_locks: Dict[str, asyncio.Lock] = {}
        self._gen_locks_guard = threading.Lock()

    # ------------------------------------------------------------------
    # 视频元数据
    # ------------------------------------------------------------------

    def get_video_meta_map(self) -> Dict[str, VideoMeta]:
        """video_id -> VideoMeta，一次全桶列举，TTL 缓存。"""
        with self._lock:
            if self._meta_map is not None and time.time() - self._meta_at < META_CACHE_TTL:
                return self._meta_map

        mapping: Dict[str, VideoMeta] = {}
        try:
            for obj in self._minio.list_objects(
                MINIO_BUCKET_RAW, prefix="raw/", recursive=True
            ):
                if not obj.etag:
                    continue
                # 解析路径: raw/{device_id}/{timestamp}/{camera_view}.mp4
                parts = obj.object_name.replace("raw/", "").split("/")
                if len(parts) < 3:
                    continue
                m = re.search(r"(\d{4}-\d{2}-\d{2})", obj.object_name)
                mapping[obj.etag[:8]] = VideoMeta(
                    video_id=obj.etag[:8],
                    object_name=obj.object_name,
                    device_id=parts[0],
                    timestamp=parts[1],
                    camera_view=os.path.splitext(parts[2])[0],
                    content_date=m.group(1) if m else "",
                    uploaded_date=(
                        obj.last_modified.date().isoformat() if obj.last_modified else ""
                    ),
                    size_bytes=obj.size or 0,
                )
        except Exception as e:
            logger.warning(f"读取视频元数据失败: {e}")
            return {}

        with self._lock:
            self._meta_map = mapping
            self._meta_at = time.time()
        return mapping

    def resolve_video(self, video_id: str) -> Optional[VideoMeta]:
        """按 video_id 解析原始视频对象；不存在（已删除）返回 None"""
        return self.get_video_meta_map().get(video_id)

    # ------------------------------------------------------------------
    # 媒体生成（async 入口，阻塞操作走 to_thread）
    # ------------------------------------------------------------------

    async def get_frame_image(self, video_id: str, frame_index: int) -> bytes:
        """获取标注帧 JPEG：缓存命中直接返回，未命中从原始视频按需抽取"""
        key = f"frames/{video_id}/{frame_index:06d}.jpg"
        data = await asyncio.to_thread(self._read_cache_object, key)
        if data is not None:
            return data
        lock = self._get_gen_lock(key)
        try:
            async with lock:
                # 取锁后重查缓存（并发请求只有一个执行 ffmpeg）
                data = await asyncio.to_thread(self._read_cache_object, key)
                if data is not None:
                    return data
                return await asyncio.to_thread(
                    self._generate_frame, video_id, frame_index, key
                )
        finally:
            self._drop_gen_lock(key)

    async def get_video_clip(self, video_id: str, start_sec: float, end_sec: float) -> bytes:
        """获取视频切片 mp4：[start_sec, end_sec+1) 时间段，重编码保证边界精确"""
        key = f"clips/{video_id}/{int(start_sec):06d}-{int(end_sec):06d}.mp4"
        lock = self._get_gen_lock(key)
        try:
            async with lock:
                data = await asyncio.to_thread(self._read_cache_object, key)
                if data is not None:
                    return data
                return await asyncio.to_thread(
                    self._generate_clip, video_id, start_sec, end_sec, key
                )
        finally:
            self._drop_gen_lock(key)

    # ------------------------------------------------------------------
    # 缓存读写
    # ------------------------------------------------------------------

    def _ensure_frames_bucket(self):
        """懒创建 tesla-frames 缓存桶（幂等）"""
        with self._lock:
            if self._bucket_ready:
                return
            try:
                if not self._minio.bucket_exists(MINIO_BUCKET_FRAMES):
                    self._minio.make_bucket(MINIO_BUCKET_FRAMES)
                self._bucket_ready = True
            except S3Error as e:
                logger.warning(f"初始化帧缓存桶失败: {e}")

    def _read_cache_object(self, key: str) -> Optional[bytes]:
        """读缓存对象；不存在返回 None（S3Error 一律视为未命中）"""
        self._ensure_frames_bucket()
        try:
            resp = self._minio.get_object(MINIO_BUCKET_FRAMES, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        except S3Error:
            return None

    def _put_cache_object(self, key: str, data: bytes, content_type: str):
        """写缓存对象；失败仅告警（不影响本次响应）"""
        try:
            self._ensure_frames_bucket()
            self._minio.put_object(
                MINIO_BUCKET_FRAMES, key,
                data=io.BytesIO(data), length=len(data), content_type=content_type,
            )
        except S3Error as e:
            logger.warning(f"缓存媒体对象失败 {key}: {e}")

    # ------------------------------------------------------------------
    # ffmpeg 生成
    # ------------------------------------------------------------------

    def _probe_video(self, object_name: str, local_path: str) -> Tuple[float, int, int]:
        """ffprobe 探测 fps/分辨率，按 object_name TTL 缓存（需本地文件）"""
        with self._lock:
            cached = self._probe_cache.get(object_name)
            if cached is not None and time.time() - self._probe_at.get(object_name, 0) < PROBE_CACHE_TTL:
                return cached

        fps, width, height = 30.0, 0, 0
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate,width,height",
                 "-of", "json", local_path],
                capture_output=True, timeout=30,
            )
            info = json.loads(proc.stdout.decode() or "{}")
            streams = info.get("streams") or []
            if streams:
                stream = streams[0]
                fps = _parse_fps(stream.get("r_frame_rate"))
                width = int(stream.get("width") or 0)
                height = int(stream.get("height") or 0)
        except Exception as e:
            logger.warning(f"探测视频信息失败 {object_name}: {e}")

        with self._lock:
            self._probe_cache[object_name] = (fps, width, height)
            self._probe_at[object_name] = time.time()
        return fps, width, height

    def _download_raw_video(self, meta: VideoMeta, tmpdir: str) -> str:
        """下载原始视频到临时目录，返回本地路径"""
        local_video = os.path.join(tmpdir, "video.mp4")
        try:
            self._minio.fget_object(MINIO_BUCKET_RAW, meta.object_name, local_video)
        except S3Error as e:
            raise MediaNotFound(f"读取原始视频失败: {meta.object_name}")
        return local_video

    def _generate_frame(self, video_id: str, frame_index: int, key: str) -> bytes:
        meta = self.resolve_video(video_id)
        if not meta:
            raise MediaNotFound(f"原始视频不存在: {video_id}")

        with tempfile.TemporaryDirectory() as tmpdir:
            local_video = self._download_raw_video(meta, tmpdir)
            fps, _, _ = self._probe_video(meta.object_name, local_video)
            seek = _seek_sec(frame_index, fps)
            out_jpg = os.path.join(tmpdir, "frame.jpg")

            proc = subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{seek:.3f}", "-i", local_video,
                 "-frames:v", "1", "-q:v", "3", out_jpg],
                capture_output=True, timeout=FFMPEG_TIMEOUT_SEC,
            )
            if proc.returncode != 0 or not os.path.exists(out_jpg) or os.path.getsize(out_jpg) == 0:
                raise MediaNotFound(f"帧超出视频时长: {video_id} 第 {frame_index} 帧")

            with open(out_jpg, "rb") as f:
                data = f.read()

        self._put_cache_object(key, data, "image/jpeg")
        return data

    def _generate_clip(self, video_id: str, start_sec: float, end_sec: float, key: str) -> bytes:
        meta = self.resolve_video(video_id)
        if not meta:
            raise MediaNotFound(f"原始视频不存在: {video_id}")

        duration = end_sec - start_sec + 1  # +1：包含最后一帧所在的完整秒
        with tempfile.TemporaryDirectory() as tmpdir:
            local_video = self._download_raw_video(meta, tmpdir)
            fps, _, _ = self._probe_video(meta.object_name, local_video)
            seek = _seek_sec(start_sec, fps)
            out_mp4 = os.path.join(tmpdir, "clip.mp4")

            # 重编码（-c copy 只能切关键帧，边界不准）；+faststart 便于流式/拖动
            proc = subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{seek:.3f}", "-i", local_video,
                 "-t", f"{duration:.3f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-an", "-movflags", "+faststart", out_mp4],
                capture_output=True, timeout=FFMPEG_TIMEOUT_SEC,
            )
            if proc.returncode != 0 or not os.path.exists(out_mp4) or os.path.getsize(out_mp4) == 0:
                raise MediaNotFound(
                    f"切片生成失败: {video_id} [{start_sec}s, {end_sec}s]"
                )

            with open(out_mp4, "rb") as f:
                data = f.read()

        self._put_cache_object(key, data, "video/mp4")
        return data

    # ------------------------------------------------------------------
    # 生成锁（per cache key）
    # ------------------------------------------------------------------

    def _get_gen_lock(self, key: str) -> asyncio.Lock:
        with self._gen_locks_guard:
            lock = self._gen_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._gen_locks[key] = lock
            return lock

    def _drop_gen_lock(self, key: str):
        # 用完即释放引用；极端竞态下最多导致重复生成，结果幂等
        with self._gen_locks_guard:
            self._gen_locks.pop(key, None)


# 模块级单例：进程内 TTL 缓存跨请求生效
media_store = MediaStore()
