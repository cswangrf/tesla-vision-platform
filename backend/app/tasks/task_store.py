"""
Tesla Vision Platform - 任务状态共享存储（Redis）

API 服务与 Celery worker 是相互独立的进程/容器，任务状态必须经 Redis 共享，
否则 worker 侧的状态更新无法反映到 API 的查询接口。
每个任务对应一个 Redis Hash 键，保留 7 天。
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import redis

from app.config import REDIS_URL

TASK_KEY_PREFIX = "task:"
TASK_TTL_SEC = 7 * 24 * 3600
# 需要 JSON 序列化的字段
_JSON_FIELDS = ("video_ids", "result")

_redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _task_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}{task_id}"


def _encode(fields: Dict) -> Dict:
    """将任务字段编码为可存入 Redis Hash 的字符串字典（剔除 None）。"""
    data = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key in _JSON_FIELDS:
            data[key] = json.dumps(value, ensure_ascii=False)
        else:
            data[key] = value
    return data


def _decode(raw: Dict) -> Dict:
    """将 Redis Hash 原始字典还原为任务字段。"""
    data = dict(raw)
    for key in _JSON_FIELDS:
        if data.get(key):
            data[key] = json.loads(data[key])
    if "progress" in data:
        data["progress"] = float(data["progress"])
    return data


def create_task(task_id: str, fields: Dict) -> None:
    """创建任务记录。fields 为 TaskResponse.model_dump(mode="json") 的结果。"""
    key = _task_key(task_id)
    _redis_client.hset(key, mapping=_encode(fields))
    _redis_client.expire(key, TASK_TTL_SEC)


def get_task(task_id: str) -> Optional[Dict]:
    """读取任务记录（原始字典），不存在时返回 None。"""
    raw = _redis_client.hgetall(_task_key(task_id))
    return _decode(raw) if raw else None


def update_task(task_id: str, **fields) -> None:
    """更新任务字段（仅更新传入字段），并刷新保留时间。"""
    data = _encode(fields)
    if not data:
        return
    data["updated_at"] = datetime.now().isoformat()
    key = _task_key(task_id)
    _redis_client.hset(key, mapping=data)
    _redis_client.expire(key, TASK_TTL_SEC)


def list_tasks() -> List[Dict]:
    """列出全部任务记录（原始字典）。"""
    tasks = []
    for key in _redis_client.scan_iter(match=f"{TASK_KEY_PREFIX}*"):
        raw = _redis_client.hgetall(key)
        if raw:
            tasks.append(_decode(raw))
    return tasks
