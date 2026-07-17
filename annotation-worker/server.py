"""
Tesla Vision Platform - 标注推理微服务

支持两种模型类型:
- chinese-clip: 图像向量提取 + 零样本场景分类
- locate-anything: 开放词汇目标检测

启动方式:
    python server.py --port 8500 --model chinese-clip --model_type ViT-L-14
    python server.py --port 8501 --model locate-anything
"""

import argparse
import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

from chinese_clip import ChineseClip
from locate_anything import LocateAnything3B

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# 数据模型
# ============================================================
class ClassifyRequest(BaseModel):
    candidates: list[str]

# ============================================================
# FastAPI 应用
# ============================================================

# 模型实例（在 lifespan 中初始化）
model_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载模型，关闭时释放资源"""
    global model_instance

    # 解析命令行参数（在 uvicorn 启动前已通过 if __name__ 块设置环境变量）
    model_type = os.environ.get("INFERENCE_MODEL", "chinese-clip")
    model_variant = os.environ.get("MODEL_TYPE", "ViT-L-14")

    logger.info(f"加载模型: {model_type} (variant: {model_variant})")

    try:
        if model_type == "chinese-clip":
            model_instance = ChineseClip(model_type=model_variant)
        elif model_type == "locate-anything":
            model_instance = LocateAnything3B()
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")

        model_instance.load_model()
        logger.info("模型加载完成")
    except Exception as e:
        logger.error(f"模型加载失败 (服务将以降级模式运行): {e}", exc_info=True)
        model_instance = None

    yield  # 服务运行期间

    # 关闭时清理
    if model_instance is not None:
        del model_instance
        model_instance = None
    logger.info("推理服务已关闭")


app = FastAPI(title="Tesla Vision Inference Worker", lifespan=lifespan)


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok" if model_instance is not None else "degraded",
        "model": os.environ.get("INFERENCE_MODEL", "unknown"),
        "model_loaded": model_instance is not None,
    }


@app.post("/embed")
async def embed(image: UploadFile = File(...)):
    """
    提取图像特征向量 (Chinese-CLIP)。

    POST /embed
    Body: multipart/form-data, field "image" = JPEG/PNG 文件

    Response: {"embedding": [0.123, -0.456, ...]}
    """
    if model_instance is None:
        return {"error": "模型未加载"}, 500

    img_bytes = await image.read()
    vec = model_instance.encode(img_bytes)
    return {"embedding": vec.tolist()}


@app.post("/classify")
async def classify(req: ClassifyRequest, image: UploadFile = File(...)):
    """
    零样本图像分类 (Chinese-CLIP)。

    POST /classify
    Body: multipart/form-data
        - "image": JPEG/PNG 文件
        - "candidates": JSON {"candidates": ["标签1", "标签2", ...]}

    Response: {"tags": [{"label": "标签1", "score": 0.85}, ...]}
    """
    if model_instance is None:
        return {"error": "模型未加载"}, 500

    img_bytes = await image.read()
    tags = model_instance.zero_shot_classify(img_bytes, req.candidates)
    return {"tags": tags}


@app.post("/detect")
async def detect(req: ClassifyRequest, image: UploadFile = File(...)):
    """
    目标检测 (LocateAnything-3B / Grounding DINO)。

    POST /detect
    Body: multipart/form-data
        - "image": JPEG/PNG 文件
        - "prompts": JSON {"candidates": ["车辆", "行人", ...]}  注: 复用 candidates 字段作为检测提示

    Response: {
        "objects": [
            {"bbox": {"x": 100, "y": 50, "width": 200, "height": 150},
             "class_name": "车辆", "confidence": 0.92, "attributes": {}}
        ]
    }
    """
    if model_instance is None:
        return {"error": "模型未加载"}, 500

    img_bytes = await image.read()
    objects = model_instance.detect(img_bytes, req.candidates)
    return {"objects": objects}


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Tesla Vision Inference Worker")
    parser.add_argument("--port", type=int, default=8500,
                        help="服务端口 (默认: 8500)")
    parser.add_argument("--model", type=str,
                        choices=["chinese-clip", "locate-anything"],
                        default="chinese-clip",
                        help="模型类型")
    parser.add_argument("--model_type", type=str, default="ViT-L-14",
                        help="Chinese-CLIP 模型变体 (默认: ViT-L-14)")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="绑定地址")

    args = parser.parse_args()

    # 将参数传入环境变量供 lifespan 事件使用
    os.environ["INFERENCE_MODEL"] = args.model
    os.environ["MODEL_TYPE"] = args.model_type
    os.environ["PORT"] = str(args.port)

    logger.info(f"启动推理服务: model={args.model}, port={args.port}")

    uvicorn.run(app, host=args.host, port=args.port)
