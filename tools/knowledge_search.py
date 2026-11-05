import json
import requests
from config.setting import TIME_OUT


class KnowledgeSearch:
    def run(self, inputs):
        try:
            # 分割知识库名称 + 查询词
            kb_name, query = inputs.split(",", 1)  # 只分割第一次，防止query里有逗号

            url = "http://localhost:6605/knowledgebase/search_kb"
            data = {
                "kb_name": kb_name.strip(),  # 清理空格
                "query": query.strip()
            }

            headers = {
                "Content-Type": "application/json"
            }

            # 发送请求
            response = requests.post(
                url,
                data=json.dumps(data),
                headers=headers,
                timeout=TIME_OUT
            )

            if response.status_code == 200:
                data = response.json()
                # 修复拼写错误：resluts → results
                results = data.get("results", [])

                if not results:
                    return "未找到相关内容"

                # 拼接返回内容
                res = ""
                for d in results:
                    res += f"来源：{d.get('source', '未知')}\n"
                    res += f"内容：{d.get('page_content', '')}\n\n"
                return res
            else:
                return f"知识库搜索失败，错误码：{response.status_code}"

        except Exception as e:
            return f"知识库调用异常：{str(e)}"


# 全局实例
knowledge_search = KnowledgeSearch()