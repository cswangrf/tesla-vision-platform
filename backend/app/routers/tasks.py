"""
Tesla Vision Platform - 任务管理路由
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    TaskCreateRequest, TaskResponse, TaskStatus
)
from app.tasks.celery_app import celery_app
from app.tasks.process_video import process_video_task

router = APIRouter()

# 任务状态内存存储（生产环境应使用 Redis/DB）
_task_store: dict[str, TaskResponse] = {}


@router.post("/process", response_model=TaskResponse)
async def create_processing_task(req: TaskCreateRequest):
    """
    提交视频处理任务（抽帧 + 标注）。
    通过 Celery 异步执行。
    """
    task_id = str(uuid.uuid4())[:8]

    task_response = TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_ids=req.video_ids,
        progress=0.0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    _task_store[task_id] = task_response

    # 提交 Celery 异步任务
    celery_task = process_video_task.delay(task_id, req.video_ids)

    return task_response


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """
    查询任务状态和进度。
    """
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    列出所有任务。
    """
    tasks = list(_task_store.values())
    if status:
        tasks = [t for t in tasks if t.status == status]

    # 按创建时间倒序
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    取消正在执行的任务。
    """
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(status_code=400, detail="任务已完成或已失败，无法取消")

    # 尝试撤销 Celery 任务
    celery_app.control.revoke(task_id, terminate=True)

    task.status = TaskStatus.FAILED
    task.error = "用户取消"
    task.updated_at = datetime.now()

    return {"task_id": task_id, "status": "cancelled"}
