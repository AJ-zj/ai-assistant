import os
from dotenv import load_dotenv

load_dotenv()
import shutil
from typing import List
import jieba
from langchain_openai import OpenAIEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException, APIRouter, UploadFile, File, Form, Body, Depends

from db_server.base import get_db, KnowledgeBase
from sqlalchemy.orm import Session
from db_server.knowledge_base_repository import add_kb_to_db, del_kb_from_db, list_kb_from_db
from config.setting import KB_DIR, FILE_STORAGE_DIR
from .loader.load import data_loader

kb_router = APIRouter(prefix="/knowledgebase", tags=["knowledgebase Bases Management"])

os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(FILE_STORAGE_DIR, exist_ok=True)

embedding = OpenAIEmbeddings(
    api_key=os.getenv("SILICONFLOW_API_KEY", ""),
    base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    model="BAAI/bge-large-zh-v1.5"
)

# ====================== 数据校验模型 ======================
class KBCreateRequest(BaseModel):
    kb_name: str = Field(..., min_length=1, max_length=50, description="知识库名称")
    kb_info: str = Field(default="", max_length=200, description="知识库描述")

    @field_validator("kb_name")
    def validate_kb_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("知识库名称不能为空")
        if "/" in v or "\\" in v or "." in v or ".." in v:
            raise ValueError("名称不能包含 / \\ . .. 等非法字符")
        return v

class KBSearchRequest(BaseModel):
    kb_name: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, max_length=500)

class DeleteDocsRequest(BaseModel):
    file_names: List[str] = Field(...)
    kb_name: str = Field(..., min_length=1)

# ====================== 接口 ======================
@kb_router.post("/create_kb")
async def create_kb(
    request: KBCreateRequest,
    db: Session = Depends(get_db)
):
    kb_name = request.kb_name
    kb_info = request.kb_info

    kb_path = os.path.join(KB_DIR, kb_name)
    if os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库已存在")

    os.makedirs(kb_path, exist_ok=True)
    add_kb_to_db(db, kb_name, kb_info)
    return {"message": f"知识库 {kb_name} 创建成功"}

@kb_router.delete("/delete_kb")
async def delete_kb(
    kb_name: str,
    db: Session = Depends(get_db)
):
    kb_path = os.path.join(KB_DIR, kb_name)
    kb_files_path = os.path.join(FILE_STORAGE_DIR, kb_name)

    if not os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库不存在")

    shutil.rmtree(kb_path, ignore_errors=True)
    if os.path.exists(kb_files_path):
        shutil.rmtree(kb_files_path, ignore_errors=True)

    del_kb_from_db(db, kb_name)
    return {"message": f"知识库 {kb_name} 已删除"}

@kb_router.get("/list_kb")
@kb_router.get("/list_kbs")
async def list_kb(db: Session = Depends(get_db)):
    kb_list = list_kb_from_db(db)
    return {"knowledgebases": kb_list}

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.csv', '.md'}

@kb_router.post("/upload_docs")
async def upload_docs(
    files: List[UploadFile] = File(...),
    kb_name: str = Form(..., min_length=1),
    chunk_size: int = Form(128, ge=64, le=1024),
    overlap: int = Form(20, ge=0, le=200)
):
    for file in files:
        _, ext = os.path.splitext(file.filename)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}")

    kb_path = os.path.join(KB_DIR, kb_name)
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库不存在")

    kb_file_storage_path = os.path.join(FILE_STORAGE_DIR, kb_name)
    os.makedirs(kb_file_storage_path, exist_ok=True)

    try:
        vectorstore = FAISS.load_local(kb_path, embedding, allow_dangerous_deserialization=True)
    except Exception:
        init_doc = Document(page_content="init")
        vectorstore = FAISS.from_documents([init_doc], embedding, normalize_L2=True)

    total_count = len(files)
    success_count = 0
    failed_count = 0
    success_files = []
    failed_files = []
    
    for file in files:
        try:
            file_path = os.path.join(kb_file_storage_path, file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())

            docs = data_loader.load_file(file_path)

            splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap, separators=["\n\n", "\n", " ", "。", "！", "？"])
            chunks = splitter.split_documents(docs)
            
            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                vectorstore.add_documents(batch)
            
            success_count += 1
            success_files.append(file.filename)
        except Exception as e:
            failed_count += 1
            failed_files.append({"name": file.filename, "error": str(e)})

    vectorstore.save_local(kb_path)
    return {
        "total": total_count,
        "success": success_count,
        "failed": failed_count,
        "success_files": success_files,
        "failed_files": failed_files
    }

@kb_router.post("/delete_docs")
async def delete_docs(
    request: DeleteDocsRequest
):
    kb_name = request.kb_name
    file_names = request.file_names

    kb_path = os.path.join(KB_DIR, kb_name)
    kb_files_path = os.path.join(FILE_STORAGE_DIR, kb_name)

    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="知识库不存在")

    vector_store = FAISS.load_local(kb_path, embedding, allow_dangerous_deserialization=True)
    success_files = []
    failed_files = {}

    for file_name in file_names:
        file_path = os.path.join(kb_files_path, file_name)
        if not os.path.exists(file_path):
            failed_files[file_name] = "文件不存在"
            continue

        try:
            os.remove(file_path)
            ids = [k for k, v in vector_store.docstore._dict.items() if v.metadata.get("source", "").lower().endswith(file_name.lower())]
            if ids:
                vector_store.delete(ids)
                success_files.append(file_name)
            else:
                failed_files[file_name] = "未找到向量"
        except Exception as e:
            failed_files[file_name] = str(e)

    vector_store.save_local(kb_path)
    return {"success": success_files, "failed": failed_files}

@kb_router.post("/search_kb")
async def search_kb(request: KBSearchRequest):
    kb_name = request.kb_name
    query = request.query

    kb_path = os.path.join(KB_DIR, kb_name)
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="知识库不存在")

    vector_store = FAISS.load_local(kb_path, embedding, allow_dangerous_deserialization=True)
    contexts = vector_store.similarity_search(query, k=3)

    return {
        "results": [
            {"sources": ctx.metadata.get("source", ""), "page_contents": ctx.page_content}
            for ctx in contexts
        ]
    }


class SearchAllKbsRequest(BaseModel):
    query: str = Field(..., min_length=1)


@kb_router.post("/search_all_kbs")
async def search_all_kbs(request: SearchAllKbsRequest):
    query = request.query
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

    return {"results": all_results}