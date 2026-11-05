import asyncio
import os
from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, UploadFile, Form, Request
from fastapi.responses import StreamingResponse
from tools.tools_select import tools
from typing import List, AsyncIterable, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from config.prompt import PROMPT_TEMPLATES
from config.setting import (
    chat_model_name, api_key, base_url, TIME_OUT, TEMP_FILE_STORAGE_DIR
)
from db_server.base import session
from db_server.knowledge_base_repository import list_kb_from_db
from tools.code_interpreter import code_interpreter
from utils.loader_doc import data_loader
import json

chat_router = APIRouter(prefix='/chat', tags=['chat 对话'])


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="用户输入问题")
    sys_prompt: str = Field(default="You are a helpful assistant.", description="系统提示")
    history_len: int = Field(default=-1, ge=-1, description="历史对话长度")
    temperature: float = Field(default=0.5, ge=0.0, le=2.0, description="随机性")
    max_tokens: int = Field(default=1024, ge=1, le=4096, description="最大token数")
    session_id: str = Field(default="default", min_length=1, description="会话id")
    history: List[str] = Field(default=[], description="历史对话")

    @field_validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError('查询内容不能为空')
        return v


async def files_rag(files: List[UploadFile], uuid: str):
    kb_file_storage_path = os.path.join(TEMP_FILE_STORAGE_DIR, uuid)
    result = []
    os.makedirs(kb_file_storage_path, exist_ok=True)

    if files:
        for file in files:
            file_path = os.path.join(kb_file_storage_path, file.filename)
            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)

    for filename in os.listdir(kb_file_storage_path):
        file_path = os.path.join(kb_file_storage_path, filename)
        if os.path.isfile(file_path):
            docs = data_loader.get_loader(file_path)
            file_content = "\n".join([doc.page_content for doc in docs])
            result.append(f"document:{file_path}\ncontent:{file_content}\n")

    return "".join(result)


@chat_router.post("/agent_chat")
async def agent_chat(
    req: Request,
    files: Optional[List[UploadFile]] = None
):
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

    query = request_obj.query
    sys_prompt = request_obj.sys_prompt
    history_len = request_obj.history_len
    temperature = request_obj.temperature
    max_tokens = request_obj.max_tokens
    session_id = request_obj.session_id
    history = request_obj.history

    documents = await files_rag(files, session_id)

    try:
        history = [json.loads(item) for item in history]
    except:
        history = []

    if history_len > 0:
        history = history[-2 * history_len:]

    messages = []
    messages.append(SystemMessage(content=sys_prompt))

    for msg in history:
        role = msg.get('role')
        content = msg.get('content')
        if role == 'user':
            messages.append(HumanMessage(content=content))
        elif role == 'assistant':
            messages.append(AIMessage(content=content))

    user_input = query
    
    kb_context = ""
    try:
        import os
        from langchain_community.vectorstores import FAISS
        from knowledgebase_server.knowledge_route import embedding
        
        KB_DIR = "knowledgebases"
        all_results = []

        if os.path.exists(KB_DIR):
            for kb_name in os.listdir(KB_DIR):
                kb_path = os.path.join(KB_DIR, kb_name)
                if os.path.isdir(kb_path):
                    try:
                        vector_store = FAISS.load_local(kb_path, embedding, allow_dangerous_deserialization=True)
                        contexts = vector_store.similarity_search(query, k=2)
                        for ctx in contexts:
                            all_results.append({
                                "kb_name": kb_name,
                                "sources": ctx.metadata.get("source", ""),
                                "page_contents": ctx.page_content
                            })
                    except Exception as e:
                        continue
        
        if all_results:
            kb_context = "\n\n【知识库检索结果】\n"
            for idx, item in enumerate(all_results, 1):
                kb_name = item.get("kb_name", "未知")
                source = item.get("sources", "未知")
                content = item.get("page_contents", "")
                kb_context += f"\n[{idx}] 知识库: {kb_name}, 来源: {source}\n内容: {content}\n"
            print(f"知识库检索成功，找到 {len(all_results)} 条相关内容")
        else:
            print("知识库检索完成，未找到相关内容")
    except Exception as e:
        print(f"知识库检索异常: {e}")
    
    if documents:
        user_input += f"\n\n参考文档:\n{documents}"
    
    if kb_context:
        user_input += kb_context
        user_input += "\n\n【重要】请在回答的开头明确说明：'📚 本次回答参考了知识库内容'，然后再给出你的回答。"
    else:
        user_input += "\n\n【重要】请在回答的开头明确说明：'❌ 本次回答未使用知识库'，然后再给出你的回答。"

    messages.append(HumanMessage(content=user_input))

    async def agent_chat_iterator() -> AsyncIterable[str]:
        try:
            chat_model = ChatOpenAI(
                model=chat_model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=True,
            )

            async for chunk in chat_model.astream(messages):
                if chunk.content:
                    res = {"answer": chunk.content}
                    yield (json.dumps(res, ensure_ascii=False) + "\n").encode("utf-8")

        except asyncio.TimeoutError:
            yield json.dumps({"answer": "\n\n[超时] 模型响应超时"}, ensure_ascii=False).encode("utf-8")
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"\n\n[错误] {str(e)}"
            yield json.dumps({"answer": error_msg}, ensure_ascii=False).encode("utf-8")

    return StreamingResponse(
        agent_chat_iterator(),
        media_type="text/event-stream"
    )
