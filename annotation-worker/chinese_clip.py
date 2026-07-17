"""
Tesla Vision Platform - Chinese-CLIP 推理模块

基于 Chinese-CLIP (https://github.com/OFA-Sys/Chinese-CLIP)，
提供图像向量提取和零样本文本-图像分类功能。

支持模型:
- ViT-B-16 (基础)
- ViT-L-14 (推荐，docker-compose 默认)
- ViT-L-14-336
- ViT-H-14

模型自动从 HuggingFace 下载并缓存到 /models 目录。
"""

import logging
import os
from typing import List, Dict, Tuple

import numpy as np
import torch
from PIL import Image
import io

logger = logging.getLogger(__name__)

# 模型配置映射
MODEL_CONFIGS: Dict[str, Dict] = {
    "ViT-B-16": {
        "hf_repo": "OFA-Sys/chinese-clip-vit-base-patch16",
        "embed_dim": 512,
        "input_resolution": 224,
    },
    "ViT-L-14": {
        "hf_repo": "OFA-Sys/chinese-clip-vit-large-patch14",
        "embed_dim": 768,
        "input_resolution": 224,
    },
    "ViT-L-14-336": {
        "hf_repo": "OFA-Sys/chinese-clip-vit-large-patch14-336",
        "embed_dim": 768,
        "input_resolution": 336,
    },
    "ViT-H-14": {
        "hf_repo": "OFA-Sys/chinese-clip-vit-huge-patch14",
        "embed_dim": 1024,
        "input_resolution": 224,
    },
}

DEFAULT_MODEL_TYPE = "ViT-L-14"


class ChineseClip:
    """
    Chinese-CLIP 模型封装。

    提供:
    - encode(image_bytes) -> 图像特征向量
    - zero_shot_classify(image_bytes, candidates) -> 零样本分类标签
    """

    def __init__(self, model_type: str = DEFAULT_MODEL_TYPE):
        self.model_type = model_type
        config = MODEL_CONFIGS.get(model_type, MODEL_CONFIGS[DEFAULT_MODEL_TYPE])
        self.hf_repo = config["hf_repo"]
        self.embed_dim = config["embed_dim"]
        self.input_resolution = config["input_resolution"]

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None

    def load_model(self):
        """加载 Chinese-CLIP 模型和处理器"""
        if self.model is not None:
            return

        logger.info(f"正在加载 Chinese-CLIP 模型: {self.hf_repo} (设备: {self.device})")

        try:
            from transformers import ChineseCLIPProcessor, ChineseCLIPModel

            # 设置模型缓存目录
            cache_dir = os.environ.get("TRANSFORMERS_CACHE", "/models")
            os.makedirs(cache_dir, exist_ok=True)

            self.processor = ChineseCLIPProcessor.from_pretrained(
                self.hf_repo,
                cache_dir=cache_dir,
            )
            self.model = ChineseCLIPModel.from_pretrained(
                self.hf_repo,
                cache_dir=cache_dir,
            ).to(self.device)
            self.model.eval()

            logger.info(f"Chinese-CLIP ({self.model_type}) 加载完成 (embed_dim={self.embed_dim})")

        except ImportError:
            # 降级方案: 使用 CN-CLIP 库
            logger.warning("transformers.ChineseCLIPProcessor 不可用，尝试使用 cn_clip")
            try:
                import cn_clip.clip as clip
                from cn_clip.clip import load_from_name

                self.model, self.processor = load_from_name(
                    f"ViT-{self.model_type.split('-')[1]}",
                    device=self.device,
                    download_root="/models",
                )
                self.model.eval()
                logger.info(f"Chinese-CLIP 通过 cn_clip 加载完成")
            except ImportError:
                raise RuntimeError(
                    "无法加载 Chinese-CLIP 模型。请安装 transformers>=4.36.0 或 cn-clip。"
                )

    def encode(self, image_bytes: bytes) -> np.ndarray:
        """
        提取图像的特征向量。

        Args:
            image_bytes: JPEG/PNG 图像字节数据

        Returns:
            shape (embed_dim,) 的 float32 numpy 数组
        """
        self.load_model()

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            logger.error(f"打开图像失败: {e}")
            return np.zeros(self.embed_dim, dtype=np.float32)

        with torch.no_grad():
            # 尝试使用 HuggingFace processor
            try:
                inputs = self.processor(
                    images=image,
                    return_tensors="pt",
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                outputs = self.model.get_image_features(**inputs)
            except (AttributeError, TypeError):
                # 降级: cn_clip 方式
                try:
                    from cn_clip.clip import load_from_name
                    # 简单预处理
                    import torchvision.transforms as T
                    transform = T.Compose([
                        T.Resize(self.input_resolution, interpolation=T.InterpolationMode.BICUBIC),
                        T.CenterCrop(self.input_resolution),
                        T.ToTensor(),
                        T.Normalize(
                            (0.48145466, 0.4578275, 0.40821073),
                            (0.26862954, 0.26130258, 0.27577711),
                        ),
                    ])
                    image_tensor = transform(image).unsqueeze(0).to(self.device)
                    outputs = self.model.encode_image(image_tensor)
                except Exception:
                    return np.zeros(self.embed_dim, dtype=np.float32)

        embedding = outputs.cpu().numpy().flatten().astype(np.float32)

        # L2 归一化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def zero_shot_classify(
        self,
        image_bytes: bytes,
        candidates: List[str],
        top_k: int = 5,
    ) -> List[Dict]:
        """
        对图像进行零样本分类。

        Args:
            image_bytes: JPEG/PNG 图像字节数据
            candidates: 候选文本标签列表，如 ["高速公路", "城市街道", "雨天"]
            top_k: 返回 Top-K 结果

        Returns:
            [{"label": "高速公路", "score": 0.85}, ...]
        """
        self.load_model()

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        with torch.no_grad():
            try:
                # HuggingFace processor 方式
                inputs = self.processor(
                    text=candidates,
                    images=image,
                    return_tensors="pt",
                    padding=True,
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                outputs = self.model(**inputs)
                logits_per_image = outputs.logits_per_image  # shape (1, num_candidates)
                probs = logits_per_image.softmax(dim=1).cpu().numpy().flatten()

            except (AttributeError, TypeError):
                # cn_clip 方式
                try:
                    import cn_clip.clip as clip
                    text_tokens = clip.tokenize(candidates).to(self.device)
                    import torchvision.transforms as T
                    transform = T.Compose([
                        T.Resize(self.input_resolution, interpolation=T.InterpolationMode.BICUBIC),
                        T.CenterCrop(self.input_resolution),
                        T.ToTensor(),
                        T.Normalize(
                            (0.48145466, 0.4578275, 0.40821073),
                            (0.26862954, 0.26130258, 0.27577711),
                        ),
                    ])
                    image_tensor = transform(image).unsqueeze(0).to(self.device)
                    image_features = self.model.encode_image(image_tensor)
                    text_features = self.model.encode_text(text_tokens)

                    # Cosine similarity
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                    text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                    similarity = (image_features @ text_features.T).cpu().numpy().flatten()
                    # Softmax
                    probs = np.exp(similarity) / np.exp(similarity).sum()
                except Exception as e:
                    logger.error(f"零样本分类失败: {e}")
                    return [{"label": c, "score": 0.0} for c in candidates[:top_k]]

        # 构建结果并按分数排序
        results = []
        for label, prob in zip(candidates, probs):
            results.append({"label": label, "score": float(prob)})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
