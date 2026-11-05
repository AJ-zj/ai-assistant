"""LangGraph Agent 编排：工具调用循环（Agent Loop）。

LLM 通过 ``bind_tools`` 获得结构化 tool_calls；``tools_condition`` 判断本轮
是继续调用工具还是结束；``ToolNode`` 执行工具后把 ToolMessage 回灌 state，
再次回到 agent 节点，直到模型给出不带 tool_calls 的最终回答。

``model`` 与 ``tool_list`` 均支持注入，使离线单测无需真实 LLM / API Key。
"""

from typing import Annotated, List, Optional

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent_graph(
    model=None,
    tool_list: Optional[List[BaseTool]] = None,
    system_prompt: str = "",
):
    """构建并编译 Agent 图。

    Args:
        model: 支持 ``bind_tools`` / ``ainvoke`` 的模型；None 时用配置中的 ChatOpenAI。
        tool_list: 工具列表；None 时加载项目的 5 个 StructuredTool。
        system_prompt: 工具使用约束与回答规范，作为 SystemMessage 注入。
    """
    if model is None:
        from langchain_openai import ChatOpenAI

        from config.setting import api_key, base_url, chat_model_name

        model = ChatOpenAI(
            model=chat_model_name,
            api_key=api_key,
            base_url=base_url,
            streaming=True,
        )

    if tool_list is None:
        from tools.tools_select import tools as default_tools

        tool_list = default_tools

    tools = list(tool_list)
    bound_model = model.bind_tools(tools)

    async def call_model(state: AgentState):
        messages = list(state["messages"])
        if system_prompt and not any(
            isinstance(message, SystemMessage) for message in messages
        ):
            messages.insert(0, SystemMessage(content=system_prompt))
        # astream 产生 token 级 on_chat_model_stream 事件供 SSE 输出；
        # 聚合成一条消息后，tools_condition 才能拿到完整的 tool_calls。
        reply = None
        async for chunk in bound_model.astream(messages):
            reply = chunk if reply is None else reply + chunk
        if reply is None:
            reply = AIMessage(content="")
        return {"messages": [reply]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile()
