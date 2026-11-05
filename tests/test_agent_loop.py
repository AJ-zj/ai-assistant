"""Agent Loop 离线验证：不需要真实 LLM、API Key 或向量库。

运行：
    python -m unittest discover -s tests -v

用脚本化的假模型 + 无害 echo 工具，验证 LangGraph 的编排行为：
1. 模型产出 tool_calls 时，tools_condition 路由到 ToolNode 并执行工具；
2. ToolMessage 回灌后再次进入 agent 节点，由模型给出最终回答；
3. 无 tool_calls 时图直接结束；
4. system_prompt 被注入首轮消息。
"""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from agent.graph import build_agent_graph


def echo(text: str) -> str:
    """无副作用的测试工具。"""
    return f"echo:{text}"


def make_tools():
    return [
        StructuredTool.from_function(
            func=echo,
            name="echo",
            description="回显输入文本，用于验证工具调用链路",
        )
    ]


class ScriptedModel:
    """按脚本依次返回 AIMessage，不联网、不调用真实模型。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.bound_tools = None
        self.seen_messages = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def astream(self, messages):
        self.seen_messages.append(list(messages))
        yield self.replies.pop(0)


class AgentLoopTest(unittest.TestCase):
    def test_tool_call_then_final_answer(self):
        tool_call = {
            "name": "echo",
            "args": {"text": "hello"},
            "id": "call_1",
            "type": "tool_call",
        }
        model = ScriptedModel(
            [
                AIMessage(content="", tool_calls=[tool_call]),
                AIMessage(content="工具返回已处理"),
            ]
        )
        graph = build_agent_graph(
            model=model,
            tool_list=make_tools(),
            system_prompt="测试用系统提示",
        )

        result = asyncio.run(
            graph.ainvoke({"messages": [HumanMessage(content="请回显 hello")]})
        )
        messages = result["messages"]

        self.assertEqual(model.bound_tools[0].name, "echo")
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].content, "echo:hello")
        self.assertEqual(messages[-1].content, "工具返回已处理")
        self.assertEqual(len(model.seen_messages), 2)
        self.assertIn("测试用系统提示", model.seen_messages[0][0].content)

    def test_no_tool_call_ends_immediately(self):
        model = ScriptedModel([AIMessage(content="直接回答")])
        graph = build_agent_graph(model=model, tool_list=make_tools())

        result = asyncio.run(
            graph.ainvoke({"messages": [HumanMessage(content="你好")]})
        )

        self.assertEqual(result["messages"][-1].content, "直接回答")
        self.assertEqual(len(model.seen_messages), 1)
        self.assertFalse(
            any(isinstance(m, ToolMessage) for m in result["messages"])
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
