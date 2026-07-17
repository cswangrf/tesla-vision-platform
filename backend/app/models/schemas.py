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
