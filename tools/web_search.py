import os
import requests
from config.setting import TIME_OUT

class WebSearch:
    def __init__(self, api_key):
        self.api_key = api_key

    def run(self, query):
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",  # 必须加，否则接口报错
            "num": 5,             # 返回 5 条结果
        }

        try:
            response = requests.get(url, params=params, timeout=TIME_OUT)
            if response.status_code != 200:
                return f"搜索失败，错误码：{response.status_code}"

            data = response.json()
            organic_results = data.get("organic_results", [])

            if not organic_results:
                return "未搜索到相关内容"

            # 拼接结果
            result_text = ""
            for idx, res in enumerate(organic_results[:5], 1):
                title = res.get("title", "无标题")
                snippet = res.get("snippet", "无简介")
                link = res.get("link", "无链接")
                result_text += f"【结果{idx}】\n标题：{title}\n简介：{snippet}\n链接：{link}\n\n"

            return result_text

        except requests.RequestException as e:
            return f"搜索请求异常：{str(e)}"

# 全局实例
web_search = WebSearch(os.getenv("SERPAPI_API_KEY", ""))