import json
import logging
from datetime import date
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
            "description": "根据语义标签、检测目标和时间范围搜索相关视频片段并统计检测目标分布",
            "parameters": {
                "type": "object",
                "properties": {
                    "global_tags": {"type": "array", "items": {"type": "string"}},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "time_range": {
                        "type": "string",
                        "description": "时间范围，格式 'YYYY-MM-DD' 或 'YYYY-MM-DD 至 YYYY-MM-DD'",
                    },
                }
            }
        }
    }
]

@router.post("/query")
async def chat_query(payload: dict):
    history = payload.get("history", [])
    user_msg = payload["message"]

    # 注入当前日期，模型才能把"今天/最近"等表述换算成具体时间范围
    system_date = {
        "role": "system",
        "content": f"当前日期是 {date.today().isoformat()}。"
                   f"涉及时间的查询请把时间范围换算成 YYYY-MM-DD 格式作为 time_range 参数。",
    }

    response = ollama.chat(
        messages=[system_date] + history + [{"role": "user", "content": user_msg}],
        tools=TOOLS
    )

    if response.tool_calls:
        try:
            tool_call = response.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            # 检索标注数据（标签 / 目标 / 时间范围筛选 + 分布统计）
            results = await spark.search(
                args.get("global_tags"),
                args.get("objects"),
                args.get("time_range"),
            )
            # 将工具结果附加到对话，继续生成回复（带上用户原始问题，否则模型不知道在回答什么）
            final_response = ollama.chat_with_tool_result(
                results, [system_date] + history + [{"role": "user", "content": user_msg}]
            )
            return {"reply": final_response, "videos": results}
        except Exception as e:
            # 工具调用失败时退化为普通回复，避免整个接口 500
            logger.error(f"工具调用失败: {e}")
            return {"reply": response.content, "videos": []}

    return {"reply": response.content, "videos": []}