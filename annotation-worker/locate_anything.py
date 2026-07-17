"""
Tesla Vision Platform - LocateAnything-3B 推理模块

基于 Grounding DINO / 开放词汇目标检测模型，
根据文本提示检测图像中的目标边界框。

提供:
- detect(image_bytes, prompts) -> 检测到的目标列表

模型选择:
- 默认使用 Grounding DINO (groundingdino) 作为轻量级方案
- 可选 Florence-2 微调版本 (需要单独下载权重)
"""

import logging
from typing import List, Dict, Any

import numpy as np
import torch
from PIL import Image
import io

logger = logging.getLogger(__name__)

# 默认模型配置
DEFAULT_MODEL_CONFIG = "IDEA-Research/grounding-dino-base"


class LocateAnything3B:
    """
    LocateAnything-3B 目标检测模型。

    基于开放词汇检测，可根据任意文本提示检测目标。
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_CONFIG):
        self.model_name = model_name
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self.box_threshold = 0.25
        self.text_threshold = 0.25

    def load_model(self):
        """加载检测模型"""
        if self.model is not None:
            return

        logger.info(f"正在加载 LocateAnything 模型: {self.model_name} (设备: {self.device})")

        try:
            from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
                self.model_name,
            ).to(self.device)
            self.model.eval()

            logger.info("LocateAnything (Grounding DINO) 加载完成")

        except ImportError as e:
            logger.warning(f"Grounding DINO 不可用 ({e})，将使用简化实现")

        except Exception as e:
            logger.error(f"加载目标检测模型失败: {e}")
            # 不抛出异常，允许降级运行

    def detect(
        self,
        image_bytes: bytes,
        prompts: List[str],
        box_threshold: float = 0.25,
        text_threshold: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """
        检测图像中与文本提示匹配的目标。

        Args:
            image_bytes: JPEG/PNG 图像字节数据
            prompts: 文本提示列表，如 ["车辆", "行人", "交通标志"]
            box_threshold: 框置信度阈值
            text_threshold: 文本匹配阈值

        Returns:
            [
                {
                    "bbox": {"x": 100, "y": 50, "width": 200, "height": 150},
                    "class_name": "车辆",
                    "confidence": 0.92,
                    "attributes": {}
                },
                ...
            ]
        """
        self.load_model()

        # 如果模型没有成功加载，返回空结果
        if self.model is None:
            logger.warning("检测模型未加载，返回空结果")
            return []

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_w, img_h = image.size

            # 将提示拼接为 Grounding DINO 格式
            text = ". ".join(prompts) + "."

            inputs = self.processor(
                images=image,
                text=text,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)

            # 后处理
            results = self.processor.post_process_grounded_object_detection(
                outputs,
                inputs["input_ids"],
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                target_sizes=torch.tensor([(img_h, img_w)]),
            )

            # 解析结果
            if not results or len(results) == 0:
                return []

            detections = results[0]
            objects = []

            boxes = detections.get("boxes", [])
            labels = detections.get("labels", [])
            scores = detections.get("scores", [])

            for box, label, score in zip(boxes, labels, scores):
                x1, y1, x2, y2 = box.tolist()
                objects.append({
                    "bbox": {
                        "x": float(x1),
                        "y": float(y1),
                        "width": float(x2 - x1),
                        "height": float(y2 - y1),
                    },
                    "class_name": label,
                    "confidence": float(score),
                    "attributes": {},
                })

            return objects

        except Exception as e:
            logger.error(f"目标检测失败: {e}")
            return self._fallback_detect(image_bytes, prompts)

    def _fallback_detect(
        self,
        image_bytes: bytes,
        prompts: List[str],
    ) -> List[Dict[str, Any]]:
        """
        降级检测方案：当主模型不可用时使用 OpenCV 传统方法。

        使用简单的颜色/边缘检测作为兜底。
        在生产环境中应确保主模型正常加载。
        """
        try:
            import cv2

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_array = np.array(image)
            img_h, img_w = img_array.shape[:2]

            objects = []

            # 对于 "交通标志"，使用红色区域检测作为替代方案
            if any(p in "交通标志红绿灯" for p in prompts):
                hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)

                # 红色范围
                lower_red1 = np.array([0, 70, 50])
                upper_red1 = np.array([10, 255, 255])
                lower_red2 = np.array([170, 70, 50])
                upper_red2 = np.array([180, 255, 255])

                mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
                mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
                mask = mask1 | mask2

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area < 100:
                        continue
                    x, y, w, h = cv2.boundingRect(contour)
                    objects.append({
                        "bbox": {
                            "x": float(x),
                            "y": float(y),
                            "width": float(w),
                            "height": float(h),
                        },
                        "class_name": "交通标志",
                        "confidence": 0.5,
                        "attributes": {"method": "fallback_color"},
                    })

            # 对于 "车辆"/"行人"，使用简单的运动检测不可行（静态帧），
            # 此处仅作为结构占位，实际使用应加载主模型
            logger.info(f"降级检测完成: 找到 {len(objects)} 个目标 (颜色检测)")
            return objects

        except Exception as e:
            logger.error(f"降级检测也失败: {e}")
            return []
