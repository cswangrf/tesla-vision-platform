import json
from fastapi import APIRouter
from app.services.ollama_client import OllamaClient
from app.services.spark_client import SparkQueryClient

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
        model="qwen2.5:7b",
        messages=history + [{"role": "user", "content": user_msg}],
        tools=TOOLS
    )

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        # 执行 Spark SQL 或向量检索
        results = spark.search(args["global_tags"], args["objects"])
        # 将工具结果附加到对话，继续生成回复
        final_response = ollama.chat_with_tool_result(results)
        return {"reply": final_response, "videos": results}

    return {"reply": response.content, "videos": []}