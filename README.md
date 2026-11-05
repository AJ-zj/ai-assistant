# 本地私有知识库 AI 助手

基于 **FastAPI + Gradio + LangChain** 的私有知识库问答助手：上传个人文档即可构建本地向量索引，提问时跨知识库检索并在上下文中标注来源，通过 SSE 流式返回回答。

> 定位：单 Agent 方向的知识库助手工程实践。当前主链路为「检索增强对话」，工具编排接入见 Roadmap。

## 功能

| 模块 | 能力 |
|---|---|
| 知识库管理 | 创建 / 删除知识库，上传 PDF / TXT / CSV / MD；扩展名白名单 + 文件名非法字符校验 |
| 文档摄入 | `RecursiveCharacterTextSplitter` 按可配置 `chunk_size` / `overlap` 切片，BGE-large-zh-v1.5 向量化写入 FAISS，SQLite 保存元数据 |
| 检索问答 | 遍历已建知识库做相似度检索，聚合片段并附带「知识库名 + 来源文件」注入上下文；要求模型在回答开头声明是否使用了知识库，未命中时明确提示 |
| 多轮与流式 | `history_len` 滑动窗口裁剪、角色化消息构造；Pydantic 校验 query 长度 / temperature / max_tokens / session_id；`StreamingResponse` + 异步迭代器输出 SSE，含超时与异常处理 |
| 工具接口 | 定义 5 个 `StructuredTool` 及参数 Schema：知识库检索、联网搜索、代码解释器、天气、时间 |
| 前端 | Gradio 分离「智能聊天」与「知识库管理」两个页面 |

## 架构

```
Browser / Gradio (:7900)
        │  HTTP form / stream
        ▼
FastAPI (:6605)
  ├── /chat/agent_chat        Pydantic 校验 → history 滑窗 → 角色化 messages
  │       ├── 遍历 knowledgebases/* → FAISS.similarity_search(query, k=2)
  │       ├── 拼接「知识库名 + 来源 + 正文」到 user_input
  │       └── ChatOpenAI(SiliconFlow / DeepSeek) .astream → SSE 分块
  └── /knowledgebase/*        创建 / 删除 / 上传文档
          ├── loader (PyMuPDF 等) → RecursiveCharacterTextSplitter
          ├── OpenAIEmbeddings (BAAI/bge-large-zh-v1.5) → FAISS 本地索引
          └── SQLite / SQLAlchemy → 知识库元数据
```

## 目录结构

```
├── app_server.py                 # FastAPI 入口、路由注册 (:6605)
├── webui.py                      # Gradio 前端 (:7900)
├── chat/
│   └── chat_routes.py            # 对话主链路：校验 / 检索注入 / SSE 流式
├── knowledgebase_server/
│   ├── knowledge_route.py        # 知识库 CRUD、文档入库、向量化
│   └── loader/load.py            # 多格式文档加载
├── tools/
│   ├── tools_select.py           # 5 个 StructuredTool 定义
│   ├── knowledge_search.py       # 私有知识库检索
│   ├── web_search.py             # SerpAPI 联网搜索
│   ├── code_interpreter.py       # Python 代码执行
│   ├── weather_check.py          # 心知天气
│   └── get_time.py               # 当前时间
├── config/
│   ├── setting.py                # 模型 / 路径 / 超时配置（密钥走环境变量）
│   └── prompt.py                 # ReAct 风格 Prompt 模板
├── db_server/                    # SQLAlchemy 模型与知识库仓库
├── utils/                        # 文档加载、回调
├── webui/                        # 前端 API 客户端
└── test_api.py                   # 接口冒烟脚本
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env      # 填入 SILICONFLOW_API_KEY
python app_server.py      # 后端 http://127.0.0.1:6605
python webui.py           # 前端 http://127.0.0.1:7900
```

首次上传文档时会自动创建 FAISS 索引；`knowledgebases/`、`data/`、`temp/` 均为运行时生成目录，已在 `.gitignore` 中排除。

## 配置

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `SILICONFLOW_API_KEY` | 对话模型 / Embedding 共用密钥（必填） | — |
| `SILICONFLOW_BASE_URL` | OpenAI 兼容接口地址 | `https://api.siliconflow.cn/v1` |
| `CHAT_MODEL` | 对话模型 | `deepseek-ai/DeepSeek-R1` |
| `SERPAPI_API_KEY` | 联网搜索工具（可选） | — |
| `SENIVERSE_API_KEY` | 天气工具（可选） | — |

知识库切片参数（`/knowledgebase/upload_docs` 表单）：`chunk_size` 默认 128（64–1024）、`overlap` 默认 20（0–200）。BGE 系列模型有 512 token 上限，切片不宜过大。

## 当前状态与 Roadmap

- [x] 多格式文档解析、切片、向量化与 FAISS 持久化
- [x] 知识库 CRUD 与 SQLite 元数据管理
- [x] 带来源标注的检索增强问答、SSE 流式输出、多轮对话
- [x] 工具集与 ReAct Prompt 模板定义
- [ ] **把工具编排接入主链路**（`bind_tools` / Agent Loop），使工具调用真正参与对话
- [ ] 补充离线评测集（Hit@K、来源标注正确率、无依据时拒答率）
- [ ] 引入混合检索（BM25 + 向量 + RRF）与跨库重排
- [ ] 服务端会话持久化（当前历史由前端传入）

## 已知限制

1. 检索为「遍历全部已建知识库、各取 Top-2 拼接」，未做跨库重排；知识库数量增多后上下文会膨胀。
2. `tools/` 下的工具集与 `config/prompt.py` 的 ReAct 模板已定义，但当前 `/chat/agent_chat` 主链路直接调用 LLM 生成，未接入工具调用循环。
3. 暂未包含离线评测集与自动化测试，仅提供 `test_api.py` 接口冒烟脚本；README 中的描述均为功能说明，不代表效果指标。
4. 会话历史由前端传入，服务端不做持久化；多实例部署时会话不共享。
5. `FAISS.load_local(..., allow_dangerous_deserialization=True)` 仅用于加载本项目自建索引，请勿加载来源不明的索引文件。

## 安全说明

所有 API Key 均通过 `.env` / 环境变量注入，仓库内不含任何凭据；`.env` 已被忽略，请勿提交。

## License

CC0 1.0 Universal（见 [LICENSE](LICENSE)）
