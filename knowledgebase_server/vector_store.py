"""ChromaDB 向量库封装。

每个知识库对应一个独立的 persist_directory，collection 名统一为 ``kb``，
避免中文知识库名受 Chroma collection 命名规则限制。Chroma 使用
PersistentClient，写入即持久化，无需显式 save，也不需要反序列化开关。
"""

import os
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from config.setting import KB_DIR

COLLECTION_NAME = "kb_docs"  # Chroma 要求 3-512 字符、仅 [a-zA-Z0-9._-]
_embedding = None


def get_embedding() -> OpenAIEmbeddings:
    """延迟初始化 Embedding，未配置 API Key 时不会在导入阶段报错。"""
    global _embedding
    if _embedding is None:
        _embedding = OpenAIEmbeddings(
            api_key=os.getenv("SILICONFLOW_API_KEY", ""),
            base_url=os.getenv(
                "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
            ),
            model="BAAI/bge-large-zh-v1.5",
            # 默认会用 tiktoken 把文本编码成 token-id 数组发到 /embeddings，
            # SiliconFlow 只接受字符串数组，否则返回 400。
            check_embedding_ctx_length=False,
        )
    return _embedding


def get_vectorstore(kb_name: str) -> Chroma:
    persist_dir = os.path.join(KB_DIR, kb_name)
    os.makedirs(persist_dir, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embedding(),
        persist_directory=persist_dir,
    )


def add_documents(kb_name: str, docs: List[Document]) -> int:
    if not docs:
        return 0
    return len(get_vectorstore(kb_name).add_documents(docs))


def similarity_search(kb_name: str, query: str, k: int = 3) -> List[Document]:
    return get_vectorstore(kb_name).similarity_search(query, k=k)


def search_kb_docs(kb_name: str, query: str, k: int = 3) -> List[dict]:
    """检索指定知识库，返回与 /knowledgebase/search_kb 相同的结构。"""
    return [
        {
            "sources": doc.metadata.get("source", ""),
            "page_contents": doc.page_content,
        }
        for doc in similarity_search(kb_name, query, k)
    ]


def search_all_kbs_docs(query: str, k: int = 2) -> List[dict]:
    """遍历全部知识库各取 Top-k，附带知识库名，供不带库名的工具调用使用。"""
    results: List[dict] = []
    if not os.path.exists(KB_DIR):
        return results
    for kb_name in os.listdir(KB_DIR):
        if not os.path.isdir(os.path.join(KB_DIR, kb_name)):
            continue
        try:
            for doc in similarity_search(kb_name, query, k):
                results.append(
                    {
                        "kb_name": kb_name,
                        "sources": doc.metadata.get("source", ""),
                        "page_contents": doc.page_content,
                    }
                )
        except Exception:
            continue
    return results


def delete_by_source(kb_name: str, file_name: str) -> int:
    """按来源文件后缀删除向量，返回删除条数。"""
    store = get_vectorstore(kb_name)
    data = store.get(include=["metadatas"])
    ids = [
        doc_id
        for doc_id, meta in zip(data.get("ids", []), data.get("metadatas") or [])
        if (meta or {}).get("source", "").lower().endswith(file_name.lower())
    ]
    if ids:
        store.delete(ids=ids)
    return len(ids)
