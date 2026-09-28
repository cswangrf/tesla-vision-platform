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
from app.tasks.task_store import (
    create_task, get_task, list_tasks as list_stored_tasks, update_task,
)

router = APIRouter()


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

    # 任务状态经 Redis 共享存储（API 与 Celery worker 为独立进程/容器）
    create_task(task_id, task_response.model_dump(mode="json"))

    # 提交 Celery 异步任务，并记录 Celery 任务 ID（撤销任务时需要）
    celery_task = process_video_task.delay(task_id, req.video_ids)
    update_task(task_id, celery_task_id=celery_task.id)

    return task_response


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """
    查询任务状态和进度。
    """
    data = get_task(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskResponse.model_validate(data)


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    列出所有任务。
    """
    tasks = [TaskResponse.model_validate(data) for data in list_stored_tasks()]
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
    data = get_task(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = TaskResponse.model_validate(data)
    if task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(status_code=400, detail="任务已完成或已失败，无法取消")

    # 撤销 Celery 任务：须传 Celery 任务 ID（业务 task_id 不是 Celery ID）
    celery_task_id = data.get("celery_task_id")
    if celery_task_id:
        celery_app.control.revoke(celery_task_id, terminate=True)

    update_task(task_id, status=TaskStatus.FAILED.value, error="用户取消")

    return {"task_id": task_id, "status": "cancelled"}
