"""
Tesla Vision Platform - 标注检索路由

提供按检测目标 / 场景标签查询标注结果（连续帧片段）、run 逐帧明细、
以及按需生成的帧图 / 视频切片媒体端点。
"""

import asyncio
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import Response

from app.config import OBJECT_PROMPTS, SCENE_CANDIDATES
from app.models.schemas import (
    AnnotationFramesResponse,
    AnnotationOptionsResponse,
    AnnotationSearchResponse,
)
from app.services.media_store import MediaNotFound, media_store
from app.services.spark_client import SparkQueryClient

router = APIRouter()

# MinIO / 检索客户端（与 videos.py / stats.py 的模块级模式一致）
_search_client = SparkQueryClient()

# run 逐帧明细的帧数上限（防止超长 run 返回超大响应）
MAX_FRAME_RANGE = 5000
# 切片时长上限（秒）
MAX_CLIP_SECONDS = 3600


def _split_csv(value: Optional[str]) -> list:
    """逗号分隔的多值参数 -> 去空列表"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/options", response_model=AnnotationOptionsResponse)
async def get_options():
    """返回筛选项词表（检测目标 / 场景标签）"""
    return AnnotationOptionsResponse(objects=OBJECT_PROMPTS, tags=SCENE_CANDIDATES)


@router.get("/search", response_model=AnnotationSearchResponse)
async def search_annotations(
    objects: Optional[str] = Query(None, description="检测目标，逗号分隔"),
    tags: Optional[str] = Query(None, description="场景标签，逗号分隔"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """按检测目标 / 场景标签检索标注数据，返回连续帧片段分页列表"""
    result = await asyncio.to_thread(
        _search_client.search_runs,
        _split_csv(objects),
        _split_csv(tags),
        page,
        page_size,
    )
    return result


@router.get("/frames/{video_id}", response_model=AnnotationFramesResponse)
async def get_run_frames(
    video_id: str,
    start: int = Query(..., ge=0),
    end: int = Query(..., ge=0),
):
    """返回 run 范围内逐帧明细（含 bbox），供前端逐帧导航与画框"""
    if end < start:
        raise HTTPException(status_code=400, detail="end 不能小于 start")
    if end - start + 1 > MAX_FRAME_RANGE:
        raise HTTPException(
            status_code=400, detail=f"帧范围过大（最大 {MAX_FRAME_RANGE} 帧）"
        )
    frames = await asyncio.to_thread(_search_client.get_run_frames, video_id, start, end)
    return AnnotationFramesResponse(video_id=video_id, frames=frames)


@router.get("/frame/{video_id}/{frame_index}")
async def get_frame_image(
    video_id: str,
    frame_index: int = Path(..., ge=0),
):
    """获取标注帧 JPEG（按需从原始视频抽取，缓存于 tesla-frames 桶）"""
    try:
        data = await media_store.get_frame_image(video_id, frame_index)
    except MediaNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    # 内容寻址（video_id 由对象 etag 派生），可安全长缓存
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.get("/clip/{video_id}")
async def get_video_clip(
    request: Request,
    video_id: str,
    start_sec: float = Query(..., ge=0),
    end_sec: float = Query(..., ge=0),
):
    """获取视频切片 mp4（[start_sec, end_sec+1)，支持单段 HTTP Range）"""
    if end_sec < start_sec:
        raise HTTPException(status_code=400, detail="end_sec 不能小于 start_sec")
    if end_sec - start_sec + 1 > MAX_CLIP_SECONDS:
        raise HTTPException(
            status_code=400, detail=f"切片时长过长（最大 {MAX_CLIP_SECONDS} 秒）"
        )
    try:
        data = await media_store.get_video_clip(video_id, start_sec, end_sec)
    except MediaNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    range_header = request.headers.get("range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)$", range_header.strip())
        if m:
            start_byte = int(m.group(1))
            end_byte = int(m.group(2)) if m.group(2) else len(data) - 1
            if start_byte >= len(data):
                raise HTTPException(status_code=416, detail="Range 超出文件范围")
            return Response(
                content=data[start_byte:end_byte + 1],
                status_code=206,
                media_type="video/mp4",
                headers={
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{len(data)}",
                    "Accept-Ranges": "bytes",
                },
            )

    return Response(
        content=data,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )
