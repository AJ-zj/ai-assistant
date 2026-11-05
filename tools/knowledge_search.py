"""知识库检索工具：直接调用本地向量库，避免 HTTP 自调用造成同进程阻塞。"""

from knowledgebase_server.vector_store import search_all_kbs_docs, search_kb_docs


class KnowledgeSearch:
    """inputs 支持两种写法：

    - ``知识库名,查询词``：检索指定知识库
    - ``查询词``：遍历全部知识库各取 Top-2
    """

    def run(self, inputs: str) -> str:
        try:
            if "," in inputs or "，" in inputs:
                kb_name, query = inputs.replace("，", ",").split(",", 1)
                kb_name, query = kb_name.strip(), query.strip()
            else:
                kb_name, query = "", inputs.strip()

            if not query:
                return "查询内容不能为空"

            if kb_name:
                results = [
                    dict(item, kb_name=kb_name)
                    for item in search_kb_docs(kb_name, query, k=3)
                ]
            else:
                results = search_all_kbs_docs(query, k=2)

            if not results:
                return "未找到相关内容"

            lines = []
            for idx, item in enumerate(results, 1):
                lines.append(
                    f"[{idx}] 知识库：{item.get('kb_name') or '未知'}"
                    f"｜来源：{item.get('sources') or '未知'}"
                )
                lines.append(f"内容：{item.get('page_contents', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"知识库调用异常：{str(e)}"


knowledge_search = KnowledgeSearch()
