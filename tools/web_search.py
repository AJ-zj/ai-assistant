"""联网搜索工具：国内接口优先，多 provider 自动降级。

优先级（按 .env 配置自动选择，前一个失败才落到下一个）：
1. 博查 Web Search API（国内，BOCHA_API_KEY）——结构化 JSON，结果为 LLM 优化
2. SerpAPI（兼容旧配置，SERPAPI_API_KEY）
3. Bing 结果页解析（免 key 兜底，零配置即可联网）

所有分支统一返回相同格式的纯文本，上层 StructuredTool 无需感知具体实现。
"""

import html
import os
import re
from pathlib import Path

import requests
from dotenv import dotenv_values

from config.setting import TIME_OUT

BOCHA_URL = "https://api.bochaai.com/v1/web-search"
SERPAPI_URL = "https://serpapi.com/search"
BING_URL = "https://cn.bing.com/search"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _env(name):
    """读环境变量；为空时回落到 .env 文件，使服务启动后补填的 Key 也能生效。"""
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    try:
        return (dotenv_values(ENV_FILE).get(name) or "").strip()
    except Exception:
        return ""


def _clean(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def _format(items, provider):
    lines = [f"[搜索来源：{provider}]"]
    for idx, (title, snippet, link) in enumerate(items, 1):
        lines.append(f"【结果{idx}】\n标题：{title}\n简介：{snippet}\n链接：{link}\n")
    return "\n".join(lines)


def _bocha(query, api_key, count):
    """博查 Web Search：POST + Bearer 鉴权，webPages.value 为结果列表。"""
    resp = requests.post(
        BOCHA_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"query": query, "freshness": "noLimit", "summary": True, "count": count},
        timeout=TIME_OUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
    pages = (resp.json().get("webPages") or {}).get("value") or []
    items = [
        (
            _clean(p.get("name")),
            _clean(p.get("snippet") or p.get("summary")),
            p.get("url", ""),
        )
        for p in pages[:count]
    ]
    if not items:
        raise RuntimeError("未返回搜索结果")
    return _format(items, "博查 Web Search API")


def _serpapi(query, api_key, count):
    resp = requests.get(
        SERPAPI_URL,
        params={"q": query, "api_key": api_key, "engine": "google", "num": count},
        timeout=TIME_OUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
    items = [
        (_clean(r.get("title")), _clean(r.get("snippet")), r.get("link", ""))
        for r in resp.json().get("organic_results", [])[:count]
    ]
    if not items:
        raise RuntimeError("未返回搜索结果")
    return _format(items, "SerpAPI")


def _bing(query, count):
    """免 key 兜底：解析 Bing 结果页 b_algo 块中的标题、摘要与链接。"""
    resp = requests.get(
        BING_URL,
        params={"q": query},
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=TIME_OUT,
    )
    resp.raise_for_status()
    items = []
    for part in re.split(r'<li class="b_algo"', resp.text)[1:]:
        block = part.split("</li>")[0]
        title_match = re.search(
            r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S
        )
        if not title_match:
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        items.append(
            (
                _clean(title_match.group(2)),
                _clean(snippet_match.group(1)) if snippet_match else "",
                html.unescape(title_match.group(1)),
            )
        )
        if len(items) >= count:
            break
    if not items:
        raise RuntimeError("结果页解析失败（页面结构可能已变化）")
    return _format(items, "Bing 结果页（免 key）")


class WebSearch:
    """按 provider 优先级自动降级；全部失败时返回可读错误，不把异常抛给 Agent。"""

    def run(self, query, count=5):
        query = (query or "").strip()
        if not query:
            return "搜索关键词为空"

        providers = []
        bocha_key = _env("BOCHA_API_KEY")
        serpapi_key = _env("SERPAPI_API_KEY")
        if bocha_key:
            providers.append(("博查", lambda: _bocha(query, bocha_key, count)))
        if serpapi_key:
            providers.append(("SerpAPI", lambda: _serpapi(query, serpapi_key, count)))
        providers.append(("Bing 免 key", lambda: _bing(query, count)))

        errors = []
        for name, call in providers:
            try:
                return call()
            except Exception as exc:  # 单通道失败继续降级，保证 Agent 链路不中断
                errors.append(f"{name}: {exc}")

        return "联网搜索全部通道均失败：\n" + "\n".join(errors)


web_search = WebSearch()
