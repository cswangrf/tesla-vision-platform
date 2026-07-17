"""
Tesla Vision Platform - Ollama LLM 客户端

通过 Ollama 的 OpenAI 兼容 API 调用 Qwen2.5:7B，
支持 Function Calling 工具增强。
"""

import json
import logging
from typing import List, Dict, Any, Optional

from openai import OpenAI

from app.config import OLLAMA_HOST, OLLAMA_MODEL

logger = logging.getLogger(__name__)


class ToolCall:
    """工具调用封装"""
    def __init__(self, func_name: str, arguments: dict):
        self.function = type("Function", (), {"name": func_name, "arguments": json.dumps(arguments)})()


class ToolResponse:
    """工具响应封装"""
    def __init__(self, content: str = "", tool_calls: Optional[List[ToolCall]] = None):
        self.content = content
        self.tool_calls = tool_calls


class OllamaClient:
    """
    Ollama LLM 客户端，支持 Function Calling。
    """

    def __init__(self):
        self.client = OpenAI(
            base_url=f"{OLLAMA_HOST}/v1",
            api_key="ollama",  # Ollama 不需要真实 key
        )
        self.model = OLLAMA_MODEL

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> ToolResponse:
        """
        发送对话请求。

        Args:
            messages: 对话历史 [{"role": "user/assistant/system", "content": "..."}]
            tools: 可用工具列表（OpenAI Function Calling 格式）
            temperature: 温度参数

        Returns:
            ToolResponse 包含回复内容和可能的工具调用
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            tool_calls = None
            if message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append(ToolCall(
                        func_name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    ))

            return ToolResponse(
                content=message.content or "",
                tool_calls=tool_calls,
            )

        except Exception as e:
            logger.error(f"Ollama chat 请求失败: {e}")
            return ToolResponse(content=f"模型调用失败: {str(e)}")

    def chat_with_tool_result(
        self,
        tool_results: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        将工具执行结果反馈给模型，生成最终回复。

        Args:
            tool_results: 工具执行的结果列表
            history: 之前的对话历史

        Returns:
            模型生成的最终自然语言回复
        """
        messages = history or []
        # 将工具结果格式化为 system 上下文
        context = "根据以下搜索结果回答用户问题:\n"
        for i, result in enumerate(tool_results):
            context += f"\n结果 {i+1}:\n"
            context += json.dumps(result, ensure_ascii=False, indent=2)

        messages.append({"role": "system", "content": context})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                stream=False,
            )
            return response.choices[0].message.content or "无法生成回复"
        except Exception as e:
            logger.error(f"生成工具结果回复失败: {e}")
            return f"处理搜索结果时出错: {str(e)}"

    def generate_summary(self, annotations: Dict[str, Any]) -> str:
        """
        根据标注数据生成自然语言摘要。

        Args:
            annotations: 包含 global_tags, objects, quality_score 等的字典

        Returns:
            自然语言摘要
        """
        prompt = f"""请根据以下自动驾驶视频标注数据生成一段简洁的中文摘要:

场景标签: {annotations.get('global_tags', [])}
检测目标: {annotations.get('objects', [])}
质量分数: {annotations.get('quality_score', 'N/A')}
帧数: {annotations.get('frame_count', 'N/A')}

请用1-2句话描述这个视频片段的内容。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                stream=False,
            )
            return response.choices[0].message.content or "无法生成摘要"
        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            return f"摘要生成失败: {str(e)}"
