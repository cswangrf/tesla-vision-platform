"""
Tesla Vision Platform - 联合标注引擎客户端

负责与 Chinese-CLIP 和 LocateAnything-3B 推理服务通信，
对每一帧图像进行全局语义标注和目标检测。
"""

import httpx
import asyncio
import logging
from typing import List, Dict, Optional

from app.config import SCENE_CANDIDATES, OBJECT_PROMPTS

logger = logging.getLogger(__name__)


class AnnotationClient:
    """
    联合标注客户端。

    同时调用 Chinese-CLIP（全局语义向量 + 零样本场景标签）
    和 LocateAnything-3B（细粒度目标检测），合并为统一标注结果。
    """

    def __init__(self, clip_url: str, lam_url: str):
        self.clip_url = clip_url
        self.lam_url = lam_url

    async def get_clip_embedding(self, image_bytes: bytes) -> List[float]:
        """获取 Chinese-CLIP 图像向量"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.clip_url}/embed",
                files={"image": ("frame.jpg", image_bytes, "image/jpeg")}
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def get_clip_tags(self, image_bytes: bytes, candidates: List[str]) -> List[Dict]:
        """Chinese-CLIP 零样本分类"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.clip_url}/classify",
                json={"candidates": candidates},
                files={"image": ("frame.jpg", image_bytes, "image/jpeg")}
            )
            resp.raise_for_status()
            return resp.json()["tags"]

    async def locate_objects(self, image_bytes: bytes, prompts: List[str]) -> List[Dict]:
        """LocateAnything-3B 目标检测"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.lam_url}/detect",
                json={"prompts": prompts},
                files={"image": ("frame.jpg", image_bytes, "image/jpeg")}
            )
            resp.raise_for_status()
            return resp.json()["objects"]

    async def annotate_frame(
        self,
        image_bytes: bytes,
        scene_candidates: Optional[List[str]] = None,
        object_prompts: Optional[List[str]] = None,
    ) -> dict:
        """
        对单帧图像进行联合标注。

        并发请求 Chinese-CLIP 和 LocateAnything-3B，
        返回包含 embedding、global_tags、objects 的统一结果。

        Args:
            image_bytes: 图像的字节数据
            scene_candidates: 场景候选词（默认使用配置中的列表）
            object_prompts: 目标检测提示词（默认使用配置中的列表）

        Returns:
            {
                "embedding": [float, ...],     # Chinese-CLIP 向量
                "global_tags": ["标签1", ...],  # 零样本分类标签
                "objects": [{bbox, class, confidence, attributes}, ...]
            }
        """
        scene_candidates = scene_candidates or SCENE_CANDIDATES
        object_prompts = object_prompts or OBJECT_PROMPTS

        try:
            clip_emb, clip_tags, objects = await asyncio.gather(
                self.get_clip_embedding(image_bytes),
                self.get_clip_tags(image_bytes, scene_candidates),
                self.locate_objects(image_bytes, object_prompts),
                return_exceptions=True,
            )

            # 处理可能的异常
            if isinstance(clip_emb, Exception):
                logger.warning(f"CLIP embedding 失败: {clip_emb}")
                clip_emb = []
            if isinstance(clip_tags, Exception):
                logger.warning(f"CLIP 标签分类失败: {clip_tags}")
                clip_tags = []
            if isinstance(objects, Exception):
                logger.warning(f"目标检测失败: {objects}")
                objects = []

            return {
                "embedding": clip_emb if isinstance(clip_emb, list) else [],
                "global_tags": [
                    t["label"] for t in (clip_tags if isinstance(clip_tags, list) else [])
                    if t.get("score", 0) > 0.3
                ],
                "objects": objects if isinstance(objects, list) else [],
            }
        except Exception as e:
            logger.error(f"标注帧失败: {e}")
            return {"embedding": [], "global_tags": [], "objects": []}

    def annotate_frame_sync(self, image_bytes: bytes) -> dict:
        """
        同步版本的 annotate_frame，用于 Celery 任务中调用。
        """
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.run(self.annotate_frame(image_bytes))
                )
                return future.result(timeout=120)
        else:
            return loop.run_until_complete(self.annotate_frame(image_bytes))
