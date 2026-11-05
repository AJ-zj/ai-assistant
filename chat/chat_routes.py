"""对话主链路：LangGraph Agent Loop + SSE 流式输出。

原实现是「纯 LLM astream + 手工遍历知识库拼 prompt」，工具定义了却从未调用。
现在由 StateGraph 决定每轮是否调用工具，ToolNode 执行后结果回灌 state，
前端仍按行解析 ``{"answer": ...}``，兼容既有 Gradio 客户端。
"""

import asyncio
import json
import os
from typing import AsyncIterable, List, Optional

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from agent.graph import build_agent_graph
from config.prompt import AGENT_SYSTEM_PROMPT
from config.setting import TEMP_FILE_STORAGE_DIR
from utils.loader_doc import data_loader

chat_router = APIRouter(prefix="/chat", tags=["chat 对话"])


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="用户输入问题")
    sys_prompt: str = Field(default="You are a helpful assistant.", description="系统提示")
    history_len: int = Field(default=-1, ge=-1, description="历史对话长度")
    temperature: float = Field(default=0.5, ge=0.0, le=2.0, description="随机性")
    max_tokens: int = Field(default=1024, ge=1, le=4096, description="最大token数")
    session_id: str = Field(default="default", min_length=1, description="会话id")
    history: List[str] = Field(default=[], description="历史对话")

    @field_validator("query")
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("查询内容不能为空")
        return v


async def files_rag(files: List[UploadFile], uuid: str):
    """把随请求上传的临时文件拼成参考文档文本。"""
    kb_file_storage_path = os.path.join(TEMP_FILE_STORAGE_DIR, uuid)
    result = []
    os.makedirs(kb_file_storage_path, exist_ok=True)

    if files:
        for file in files:
            file_path = os.path.join(kb_file_storage_path, file.filename)
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

    for filename in os.listdir(kb_file_storage_path):
        file_path = os.path.join(kb_file_storage_path, filename)
        if os.path.isfile(file_path):
            docs = data_loader.get_loader(file_path)
            file_content = "\n".join([doc.page_content for doc in docs])
            result.append(f"document:{file_path}\ncontent:{file_content}\n")

    return "".join(result)


def build_messages(request_obj: ChatRequest, documents: str) -> list:
    system_content = AGENT_SYSTEM_PROMPT
    if request_obj.sys_prompt and request_obj.sys_prompt != "You are a helpful assistant.":
        system_content += f"\n\n用户补充要求：{request_obj.sys_prompt}"

    history = []
    try:
        history = [json.loads(item) for item in request_obj.history]
    except Exception:
        history = []

    if request_obj.history_len > 0:
        history = history[-2 * request_obj.history_len :]

    messages = [SystemMessage(content=system_content)]
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    user_input = request_obj.query
    if documents:
        user_input += f"\n\n随请求上传的文档:\n{documents}"
    messages.append(HumanMessage(content=user_input))
    return messages


@chat_router.post("/agent_chat")
async def agent_chat(req: Request, files: Optional[List[UploadFile]] = None):
    form_data = await req.form()
    request_json = form_data.get("request")
    if not request_json:
        return {"code": 400, "msg": "缺少request参数"}

    try:
        request_data = json.loads(request_json)
    except json.JSONDecodeError:
        return {"code": 400, "msg": "request参数格式错误"}

    try:
        request_obj = ChatRequest(**request_data)
    except Exception as e:
        return {"code": 400, "msg": f"参数验证失败: {str(e)}"}

    documents = await files_rag(files, request_obj.session_id)
    messages = build_messages(request_obj, documents)

    async def agent_chat_iterator() -> AsyncIterable[bytes]:
        try:
            graph = build_agent_graph()
            async for event in graph.astream_events(
                {"messages": messages}, version="v2"
            ):
                kind = event.get("event")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "") if chunk else ""
                    if content:
                        yield (
                            json.dumps({"answer": content}, ensure_ascii=False) + "\n"
                        ).encode("utf-8")

                elif kind == "on_tool_start":
                    name = event.get("name", "unknown")
                    yield (
                        json.dumps(
                            {"answer": f"\n[调用工具] {name}\n"}, ensure_ascii=False
                        )
                        + "\n"
                    ).encode("utf-8")

        except asyncio.TimeoutError:
            yield json.dumps(
                {"answer": "\n\n[超时] 模型响应超时"}, ensure_ascii=False
            ).encode("utf-8")
        except Exception as e:
            yield json.dumps(
                {"answer": f"\n\n[错误] {str(e)}"}, ensure_ascii=False
            ).encode("utf-8")

    return StreamingResponse(agent_chat_iterator(), media_type="text/event-stream")
