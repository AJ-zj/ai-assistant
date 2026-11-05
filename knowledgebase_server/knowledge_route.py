"""知识库管理路由：创建 / 删除 / 上传 / 删除文档 / 检索。

向量存储由 knowledgebase_server.vector_store 统一封装（ChromaDB 持久化），
本模块只负责接口校验、文档切分与 SQLite 元数据。
"""

import os
import shutil
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from config.setting import FILE_STORAGE_DIR, KB_DIR
from db_server.base import get_db
from db_server.knowledge_base_repository import (
    add_kb_to_db,
    del_kb_from_db,
    list_kb_from_db,
)
from .loader.load import data_loader
from .vector_store import (
    add_documents,
    delete_by_source,
    search_all_kbs_docs,
    search_kb_docs,
)

load_dotenv()

kb_router = APIRouter(prefix="/knowledgebase", tags=["knowledgebase Bases Management"])

os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(FILE_STORAGE_DIR, exist_ok=True)


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
async def create_kb(request: KBCreateRequest, db: Session = Depends(get_db)):
    kb_name = request.kb_name
    kb_info = request.kb_info

    kb_path = os.path.join(KB_DIR, kb_name)
    if os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库已存在")

    os.makedirs(kb_path, exist_ok=True)
    add_kb_to_db(db, kb_name, kb_info)
    return {"message": f"知识库 {kb_name} 创建成功"}


@kb_router.delete("/delete_kb")
async def delete_kb(kb_name: str, db: Session = Depends(get_db)):
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
    return {"knowledgebases": list_kb_from_db(db)}


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv", ".md"}


@kb_router.post("/upload_docs")
async def upload_docs(
    files: List[UploadFile] = File(...),
    kb_name: str = Form(..., min_length=1),
    chunk_size: int = Form(128, ge=64, le=1024),
    overlap: int = Form(20, ge=0, le=200),
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
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                separators=["\n\n", "\n", " ", "。", "！", "？"],
            )
            chunks = splitter.split_documents(docs)

            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                add_documents(kb_name, chunks[i : i + batch_size])

            success_count += 1
            success_files.append(file.filename)
        except Exception as e:
            failed_count += 1
            failed_files.append({"name": file.filename, "error": str(e)})

    # Chroma PersistentClient 写入即落盘，无需显式 save。
    return {
        "total": total_count,
        "success": success_count,
        "failed": failed_count,
        "success_files": success_files,
        "failed_files": failed_files,
    }


@kb_router.post("/delete_docs")
async def delete_docs(request: DeleteDocsRequest):
    kb_name = request.kb_name
    file_names = request.file_names

    kb_path = os.path.join(KB_DIR, kb_name)
    kb_files_path = os.path.join(FILE_STORAGE_DIR, kb_name)

    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="知识库不存在")

    success_files = []
    failed_files = {}

    for file_name in file_names:
        file_path = os.path.join(kb_files_path, file_name)
        if not os.path.exists(file_path):
            failed_files[file_name] = "文件不存在"
            continue

        try:
            os.remove(file_path)
            deleted = delete_by_source(kb_name, file_name)
            if deleted:
                success_files.append(file_name)
            else:
                failed_files[file_name] = "未找到向量"
        except Exception as e:
            failed_files[file_name] = str(e)

    return {"success": success_files, "failed_files": failed_files}


@kb_router.post("/search_kb")
async def search_kb(request: KBSearchRequest):
    kb_path = os.path.join(KB_DIR, request.kb_name)
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="知识库不存在")

    return {"results": search_kb_docs(request.kb_name, request.query, k=3)}


class SearchAllKbsRequest(BaseModel):
    query: str = Field(..., min_length=1)


@kb_router.post("/search_all_kbs")
async def search_all_kbs(request: SearchAllKbsRequest):
    return {"results": search_all_kbs_docs(request.query, k=2)}
