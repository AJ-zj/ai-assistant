# 本地私有知识库 AI 助手

基于 **FastAPI + Gradio + LangChain + LangGraph + ChromaDB** 的私有知识库 Agent：上传个人文档即可构建本地向量索引，由 Agent 自主决定是否检索知识库或调用工具，结果通过 SSE 流式返回。

> 定位：单 Agent 方向的工程实践。工具调用由 LangGraph 的 Agent Loop 驱动，向量索引落在 ChromaDB 持久化目录。

## 功能

| 模块 | 能力 |
|---|---|
| Agent 编排 | LangGraph `StateGraph`：`bind_tools` 结构化工具调用、`tools_condition` 条件路由、`ToolNode` 执行与结果回灌 |
| 工具集 | 5 个 `StructuredTool`：知识库检索、联网搜索、代码解释器、天气、时间 |
| 知识库管理 | 创建 / 删除，上传 PDF / TXT / CSV / MD；扩展名白名单 + 文件名非法字符校验 |
| 文档摄入 | `RecursiveCharacterTextSplitter` 按可配置 `chunk_size` / `overlap` 切片，BGE-large-zh-v1.5 向量化写入 Chroma |
| 检索与溯源 | 按库检索 Top-3，或省略库名遍历全部库各取 Top-2；结果带「知识库名｜来源文件」，System Prompt 要求标注引用、无证据不编造 |
| 多轮与流式 | Pydantic 校验、`history_len` 滑窗；`astream_events` 输出 token 流与工具调用轨迹，SSE 每行一个 `{"answer": ...}` |
| 前端 | Gradio 分离「智能聊天」与「知识库管理」两个页面 |

## 架构

```
Browser / Gradio (:7900)  ── HTTP / SSE ──▶  FastAPI (:6605)
│
├── /chat/agent_chat
│     Pydantic 校验 → history 滑窗 → SystemMessage(工具使用约束) + messages
│     ▼
│     LangGraph StateGraph
│       agent : ChatOpenAI.bind_tools(5 tools).astream → 聚合为 AIMessage
│       ├─ 有 tool_calls ─▶ tools_condition ─▶ ToolNode 执行 ─▶ 结果回灌 ─┐
│       └─ 无 tool_calls ─▶ END                                          │
│                          ◀──────────────────────────────────────────┘
│     ▼
│     astream_events: on_chat_model_stream → SSE token
│                     on_tool_start        → SSE "[调用工具] xxx"
│
└── /knowledgebase/*
      loader (PyMuPDF 等) → RecursiveCharacterTextSplitter
      → OpenAIEmbeddings → Chroma(PersistentClient，每库独立目录)
      → SQLite / SQLAlchemy 保存知识库元数据
```

## 目录结构

```
├── agent/
│   └── graph.py                  # LangGraph StateGraph 编排（model/tool 可注入）
├── chat/
│   └── chat_routes.py            # 参数校验、消息构造、SSE 流式输出
├── knowledgebase_server/
│   ├── knowledge_route.py        # 知识库 CRUD、文档入库
│   ├── vector_store.py           # ChromaDB 封装：增删查、跨库检索
│   └── loader/load.py            # 多格式文档加载
├── tools/                        # 5 个 StructuredTool + 各自实现
├── config/
│   ├── setting.py                # 模型 / 路径 / 超时（密钥走环境变量）
│   └── prompt.py                 # Agent System Prompt + 早期 ReAct 模板（对照保留）
├── tests/
│   └── test_agent_loop.py        # 离线验证 Agent Loop，不需 API Key
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

`knowledgebases/`、`data/`、`temp/` 为运行时生成目录，已在 `.gitignore` 中排除。

## 配置

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `SILICONFLOW_API_KEY` | 对话模型 / Embedding 共用密钥（必填） | — |
| `SILICONFLOW_BASE_URL` | OpenAI 兼容接口地址 | `https://api.siliconflow.cn/v1` |
| `CHAT_MODEL` | 对话模型，**需支持 function calling / tool calling** | `deepseek-ai/DeepSeek-R1` |
| `SERPAPI_API_KEY` | 联网搜索工具（可选） | — |
| `SENIVERSE_API_KEY` | 天气工具（可选） | — |

知识库切片参数（`/knowledgebase/upload_docs` 表单）：`chunk_size` 默认 128（64–1024）、`overlap` 默认 20（0–200）。BGE 系列模型有 512 token 上限，切片不宜过大。

> ⚠️ 默认的 DeepSeek-R1 是推理模型，部分平台/版本不开放 tool calling。若 Agent 从不触发工具，请在 `.env` 里把 `CHAT_MODEL` 换成支持工具调用的模型（如 Qwen2.5-Instruct 系列）。

## 离线验证（不需要 API Key）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # 最小集合：langgraph langchain-core pydantic
.venv/Scripts/python -m unittest discover -s tests -v
```

| 测试 | 验证内容 | 额外依赖 |
|---|---|---|
| `tests/test_agent_loop.py` | 脚本化假模型 + 无副作用 echo 工具：模型产出 `tool_calls` 时路由到 `ToolNode` 并执行、`ToolMessage` 回灌后再次进入 agent、无 `tool_calls` 时直接结束、System Prompt 注入首轮消息 | 无 |
| `tests/test_vector_store.py` | 临时目录 + `FakeEmbeddings` 实测 Chroma 的写入、按库检索、跨库检索、按来源删除 | `langchain-chroma` / `chromadb`（未安装则自动跳过） |

两个测试都不联网、不需要任何真实 API Key，也不在仓库内留下索引文件。

## 端到端跑一次工具调用（需要 Key）

配好 `.env` 并启动服务后，向 `/chat/agent_chat` 提问「现在几点」或「北京天气」，SSE 流中应依次出现：

```
{"answer": "\n[调用工具] get_time\n"}
{"answer": "当前时间是 ..."}
```

这一步需要真实模型与 API Key，本仓库不提供凭据。

## 当前状态与 Roadmap

- [x] 多格式文档解析、切片、向量化与 ChromaDB 持久化
- [x] 知识库 CRUD 与 SQLite 元数据管理
- [x] 带来源标注的检索增强问答、SSE 流式输出、多轮对话
- [x] LangGraph Agent Loop 接入 5 个工具，工具调用轨迹可见
- [ ] 混合检索（BM25 + 向量 + RRF）与跨库重排
- [ ] 离线评测集（Hit@K、来源标注正确率、无依据拒答率、工具选择准确率）
- [ ] 会话历史服务端持久化（当前由前端传入）
- [ ] 工具执行沙箱与超时隔离

## 已知限制

1. 检索为向量单路，未做跨库重排；知识库数量增多后上下文会膨胀。
2. 工具调用依赖模型支持 tool calling；推理型模型可能不返回 `tool_calls`。
3. 暂无离线评测集，`tests/` 只覆盖 Agent Loop 编排逻辑，不代表端到端效果指标。
4. 会话历史由前端传入，服务端不做持久化；多实例部署时会话不共享。
5. `code_interpreter` 在进程内执行 Python，未做沙箱隔离，仅建议本地单用户使用。
6. 联网搜索与天气工具依赖外部 API，未配置 Key 时会返回调用异常，不影响其余工具。

## 安全说明

所有 API Key 均通过 `.env` / 环境变量注入，仓库内不含任何凭据；`.env` 已被忽略，请勿提交。

## License

CC0 1.0 Universal（见 [LICENSE](LICENSE)）
