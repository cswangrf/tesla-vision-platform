import json
import logging
from fastapi import APIRouter
from app.services.ollama_client import OllamaClient
from app.services.spark_client import SparkQueryClient

logger = logging.getLogger(__name__)

router = APIRouter()
ollama = OllamaClient()
spark = SparkQueryClient()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_videos",
            "description": "根据语义标签和检测目标搜索相关视频片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "global_tags": {"type": "array", "items": {"type": "string"}},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "time_range": {"type": "string"}
                }
            }
        }
    }
]

@router.post("/query")
async def chat_query(payload: dict):
    history = payload.get("history", [])
    user_msg = payload["message"]

    response = ollama.chat(
        messages=history + [{"role": "user", "content": user_msg}],
        tools=TOOLS
    )

    if response.tool_calls:
        try:
            tool_call = response.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            # 执行 Spark SQL 或向量检索
            results = await spark.search(args.get("global_tags"), args.get("objects"))
            # 将工具结果附加到对话，继续生成回复（带上用户原始问题，否则模型不知道在回答什么）
            final_response = ollama.chat_with_tool_result(
                results, history + [{"role": "user", "content": user_msg}]
            )
            return {"reply": final_response, "videos": results}
        except Exception as e:
            # 工具调用失败时退化为普通回复，避免整个接口 500
            logger.error(f"工具调用失败: {e}")
            return {"reply": response.content, "videos": []}

    return {"reply": response.content, "videos": []}