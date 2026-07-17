"""
Tesla Vision Platform - 视频管理路由
"""

import io
import uuid
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from minio import Minio
from minio.error import S3Error

from app.config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_RAW, MINIO_SECURE
)
from app.models.schemas import VideoUploadResponse, VideoMetadata, VideoListResponse

router = APIRouter()

# MinIO 客户端
_minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)


def _ensure_bucket():
    """确保原始视频桶存在"""
    if not _minio_client.bucket_exists(MINIO_BUCKET_RAW):
        _minio_client.make_bucket(MINIO_BUCKET_RAW)


def _get_video_metadata(object_name: str) -> dict:
    """从 MinIO 获取视频对象元数据"""
    try:
        stat = _minio_client.stat_object(MINIO_BUCKET_RAW, object_name)
        return {
            "size_bytes": stat.size,
            "uploaded_at": stat.last_modified,
        }
    except S3Error:
        return {"size_bytes": 0, "uploaded_at": datetime.now()}


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    device_id: str = Form(...),
    timestamp: str = Form(...),
    camera_view: str = Form(...),
):
    """
    上传 Tesla 视频文件，保留时间-视角目录结构。

    目录结构: /raw/{device_id}/{timestamp}/{camera_view}.mp4
    """
    _ensure_bucket()

    # 生成唯一 video_id
    video_id = str(uuid.uuid4())[:8]

    # 构建存储路径
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    storage_path = f"raw/{device_id}/{timestamp}/{camera_view}{ext}"

    # 上传到 MinIO
    # 注意: minio-py 的 put_object 要求 data 是 file-like 对象（有 .read() 方法），
    # 不能直接传 bytes，需要包装为 BytesIO
    content = await file.read()
    _minio_client.put_object(
        MINIO_BUCKET_RAW,
        storage_path,
        data=io.BytesIO(content),
        length=len(content),
        content_type="video/mp4",
    )

    return VideoUploadResponse(
        video_id=video_id,
        filename=file.filename,
        device_id=device_id,
        timestamp=timestamp,
        camera_view=camera_view,
        storage_path=f"s3://{MINIO_BUCKET_RAW}/{storage_path}",
        size_bytes=len(content),
    )


@router.get("/", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    device_id: str = Query(None),
):
    """
    列出已上传的视频文件。
    """
    _ensure_bucket()

    videos: List[VideoMetadata] = []
    objects = _minio_client.list_objects(MINIO_BUCKET_RAW, prefix="raw/", recursive=True)

    for obj in objects:
        # 解析路径: raw/{device_id}/{timestamp}/{camera_view}.mp4
        parts = obj.object_name.replace("raw/", "").split("/")
        if len(parts) < 3:
            continue

        obj_device_id = parts[0]
        obj_timestamp = parts[1]
        camera_with_ext = parts[2]
        camera_view = os.path.splitext(camera_with_ext)[0]

        if device_id and obj_device_id != device_id:
            continue

        # 解析路径中的时间戳: 格式 YYYY-MM-DD_HH-MM-SS
        try:
            parsed_ts = datetime.strptime(obj_timestamp, "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            parsed_ts = datetime.now()

        videos.append(VideoMetadata(
            video_id=obj.etag[:8] if obj.etag else str(uuid.uuid4())[:8],
            device_id=obj_device_id,
            timestamp=parsed_ts,
            camera_view=camera_view,
            duration_sec=0.0,  # 需要解析视频获取
            fps=0.0,
            resolution="unknown",
            file_size_bytes=obj.size,
            storage_path=f"s3://{MINIO_BUCKET_RAW}/{obj.object_name}",
            uploaded_at=obj.last_modified,
            status="uploaded",
        ))

    # 分页
    total = len(videos)
    start = (page - 1) * page_size
    end = start + page_size

    return VideoListResponse(
        videos=videos[start:end],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stream/{video_id}")
async def stream_video(video_id: str):
    """
    流式传输视频文件。根据 video_id 查找 MinIO 中的原始视频并返回。
    video_id 格式: {device_id}/{timestamp}/{camera_view}.mp4
    也支持短 ID (etag 前8位) 模糊匹配。
    """
    _ensure_bucket()

    objects = _minio_client.list_objects(MINIO_BUCKET_RAW, prefix="raw/", recursive=True)
    target_object = None

    for obj in objects:
        # 支持两种匹配方式：完整路径匹配 或 etag 前8位匹配
        relative_path = obj.object_name.replace("raw/", "")
        if relative_path == video_id or (obj.etag and obj.etag[:8] == video_id):
            target_object = obj
            break

    if not target_object:
        raise HTTPException(status_code=404, detail=f"视频不存在: {video_id}")

    # 流式返回 MinIO 对象
    try:
        response = _minio_client.get_object(MINIO_BUCKET_RAW, target_object.object_name)
        return StreamingResponse(
            response.stream(64 * 1024),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="{target_object.object_name.split("/")[-1]}"',
            },
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"读取视频失败: {str(e)}")


@router.delete("/{video_id}")
async def delete_video(video_id: str):
    """
    删除指定视频及其标注数据。
    """
    _ensure_bucket()

    # 查找并删除原始视频
    objects = _minio_client.list_objects(MINIO_BUCKET_RAW, prefix="raw/", recursive=True)
    deleted = 0
    for obj in objects:
        if obj.etag and obj.etag[:8] == video_id:
            _minio_client.remove_object(MINIO_BUCKET_RAW, obj.object_name)
            deleted += 1

    if deleted == 0:
        raise HTTPException(status_code=404, detail="视频不存在")

    return {"deleted": deleted, "video_id": video_id}
