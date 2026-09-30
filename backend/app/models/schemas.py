"""
Tesla Vision Platform - Pydantic 数据模型
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================
# 任务状态
# ============================================================
class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# 视频相关
# ============================================================
class VideoUploadResponse(BaseModel):
    """视频上传响应"""
    video_id: str
    filename: str
    device_id: str
    timestamp: str
    camera_view: str
    storage_path: str
    size_bytes: int


class VideoMetadata(BaseModel):
    """视频元数据"""
    video_id: str
    device_id: str
    timestamp: datetime
    camera_view: str
    duration_sec: float
    fps: float
    resolution: str
    file_size_bytes: int
    storage_path: str
    uploaded_at: datetime
    status: str = "uploaded"


class VideoListResponse(BaseModel):
    """视频列表响应"""
    videos: List[VideoMetadata]
    total: int
    page: int
    page_size: int


# ============================================================
# 标注相关
# ============================================================
class BoundingBox(BaseModel):
    """目标边界框"""
    x: float
    y: float
    width: float
    height: float


class DetectedObject(BaseModel):
    """检测到的目标"""
    bbox: BoundingBox
    class_name: str
    confidence: float
    attributes: Optional[Dict[str, Any]] = None


class FrameAnnotation(BaseModel):
    """帧标注结果"""
    video_id: str
    frame_index: int
    timestamp_sec: float
    global_embedding: Optional[List[float]] = None
    global_tags: List[str] = []
    objects: List[DetectedObject] = []
    blur_score: Optional[float] = None
    quality_score: Optional[float] = None


class AnnotationSummary(BaseModel):
    """视频标注摘要"""
    video_id: str
    total_frames: int
    annotated_frames: int
    dominant_scenes: List[str]
    object_counts: Dict[str, int]
    average_quality_score: float
    processing_status: str


# ============================================================
# 标注检索（连续帧片段）
# ============================================================
class AnnotationOptionsResponse(BaseModel):
    """标注检索筛选项（检测目标 / 场景标签词表）"""
    objects: List[str]
    tags: List[str]


class AnnotationRunObjectStat(BaseModel):
    """run 内检测目标聚合统计"""
    class_name: str
    count: int
    max_confidence: float


class AnnotationRunTagStat(BaseModel):
    """run 内场景标签聚合统计"""
    name: str
    count: int


class AnnotationRun(BaseModel):
    """连续帧片段（同一视频中连续命中的帧合并为一条）"""
    run_id: str
    video_id: str
    device_id: str = ""
    camera_view: str = ""
    content_date: str = ""
    uploaded_date: str = ""
    start_frame: int
    end_frame: int
    frame_count: int
    start_sec: float
    end_sec: float
    objects: List[AnnotationRunObjectStat] = []
    tags: List[AnnotationRunTagStat] = []
    avg_quality: float = 0.0
    has_raw_video: bool = False
    thumbnail_url: str = ""
    clip_url: str = ""


class AnnotationSearchResponse(BaseModel):
    """标注检索分页响应"""
    items: List[AnnotationRun]
    total: int
    page: int
    page_size: int


class AnnotationFramesResponse(BaseModel):
    """run 范围内逐帧明细"""
    video_id: str
    frames: List[FrameAnnotation] = []


# ============================================================
# 任务相关
# ============================================================
class TaskCreateRequest(BaseModel):
    """创建处理任务请求"""
    video_ids: List[str]
    priority: int = 0


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    status: TaskStatus
    video_ids: List[str]
    progress: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============================================================
# 对话/Chat 相关
# ============================================================
class ChatMessage(BaseModel):
    """对话消息"""
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    history: List[ChatMessage] = []


class VideoSearchResult(BaseModel):
    """视频搜索结果"""
    video_id: str
    timestamp_sec: float
    score: float
    matched_tags: List[str] = []
    matched_objects: List[str] = []
    thumbnail_url: Optional[str] = None


class ChatResponse(BaseModel):
    """对话响应"""
    reply: str
    videos: List[VideoSearchResult] = []


# ============================================================
# 搜索/查询
# ============================================================
class SearchRequest(BaseModel):
    """语义搜索请求"""
    query: str
    global_tags: Optional[List[str]] = None
    objects: Optional[List[str]] = None
    time_range: Optional[str] = None
    limit: int = 10
