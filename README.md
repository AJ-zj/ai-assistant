# 本地私有知识库 AI 助手

基于 **FastAPI + Gradio + LangChain + LangGraph + ChromaDB** 的私有知识库 Agent：上传个人文档即可构建本地向量索引，由 Agent 自主决定是否检索知识库或调用工具，结果通过 SSE 流式返回。

> 定位：单 Agent 方向的工程实践。工具调用由 LangGraph 的 Agent Loop 驱动，向量索引落在 ChromaDB 持久化目录。

## 功能

| 模块 | 能力 |
|---|---|
| Agent 编排 | LangGraph `StateGraph`：`bind_tools` 结构化工具调用、`tools_condition` 条件路由、`ToolNode` 执行与结果回灌 |
| 工具集 | 5 个 `StructuredTool`：知识库检索、联网搜索、代码解释器、天气、时间 |
| 代码解释器 | 独立 worker 线程中按需启动本地 CodeBox，不占用 FastAPI 的事件循环；异常降级为可读文本，不影响其余 4 个工具 |
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
│   ├── test_agent_loop.py        # 离线验证 Agent Loop，不需 API Key
│   ├── test_vector_store.py      # Chroma 增删查（FakeEmbeddings）
│   └── test_tool_import.py       # 事件循环内安全导入工具列表的回归测试
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
| `CHAT_MODEL` | 对话模型，**需支持 function calling / tool calling** | `deepseek-ai/DeepSeek-V3` |
| `SERPAPI_API_KEY` | 联网搜索工具（可选） | — |
| `SENIVERSE_API_KEY` | 天气工具（可选） | — |

知识库切片参数（`/knowledgebase/upload_docs` 表单）：`chunk_size` 默认 128（64–1024）、`overlap` 默认 20（0–200）。BGE 系列模型有 512 token 上限，切片不宜过大。

> 模型选择：默认 `deepseek-ai/DeepSeek-V3` 在 SiliconFlow 上实测工具调用稳定。DeepSeek-R1 等推理模型会出现不返回 `tool_calls`、直接编造时间的情况；切换模型前请确认其支持 function calling。Embedding 侧 `OpenAIEmbeddings` 必须关闭 `check_embedding_ctx_length`，否则 SDK 会发送 token-id 数组导致接口 400（代码里已处理）。

## 离线验证（不需要 API Key）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m unittest discover -s tests -v
```

| 测试 | 验证内容 | 额外依赖 |
|---|---|---|
| `tests/test_agent_loop.py` | 脚本化假模型 + 无副作用 echo 工具：模型产出 `tool_calls` 时路由到 `ToolNode` 并执行、`ToolMessage` 回灌后再次进入 agent、无 `tool_calls` 时直接结束、System Prompt 注入首轮消息 | 无 |
| `tests/test_vector_store.py` | 临时目录 + `FakeEmbeddings` 实测 Chroma 的写入、按库检索、跨库检索、按来源删除 | `langchain-chroma` / `chromadb`（未安装则自动跳过） |
| `tests/test_tool_import.py` | 在运行中的 asyncio 事件循环里导入 5 个工具并调用 `get_time`，回归验证代码解释器不再拖垮工具列表 | 完整 `requirements.txt`（缺依赖则跳过） |

全部 4 个用例均不联网、不需要真实 API Key，也不在仓库内留下索引文件。

## 端到端验证（需要 Key）

配好 `.env` 并启动服务后，向 `/chat/agent_chat` 提问「现在几点」，SSE 流中应出现：

```
{"answer": "\n[调用工具] get_time\n"}
{"answer": "当前时间是 2026-11-05 14:23:05"}
```

实测记录（2026-11-05，SiliconFlow + DeepSeek-V3）：

| 场景 | 结果 |
|---|---|
| 工具调用 | 连续 3 次「现在几点」均触发 `get_time`，SSE 出现 `[调用工具]` 轨迹，回答时间与本机时钟一致 |
| 知识库链路 | 创建知识库 → 上传 txt → BGE 向量化写入 Chroma → 提问触发 `knowledge_search` → 回答命中文档中的口令并标注「知识库名｜来源文件」→ 删除知识库清理 |
| Embedding | `/embeddings` 返回 1024 维向量；`embed_query` / `embed_documents` 均可用 |

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
2. 工具调用依赖模型支持 function calling；推理型模型可能不返回 `tool_calls`（默认 V3 已验证稳定）。
3. 暂无离线评测集，`tests/` 覆盖 Agent Loop 编排、向量库增删查与工具导入回归，不代表端到端效果指标。
4. 会话历史由前端传入，服务端不做持久化；多实例部署时会话不共享。
5. `code_interpreter` 在进程内执行 Python，未做沙箱隔离，仅建议本地单用户使用；现已改为独立 worker 线程按需启动，避免与 FastAPI 事件循环冲突。
6. 联网搜索与天气工具依赖外部 API，未配置 Key 时会返回调用异常，不影响其余工具。
7. 前端 Gradio 只在使用 `webui.py` 时需要，后端服务启动不依赖它。

## 安全说明

所有 API Key 均通过 `.env` / 环境变量注入，仓库内不含任何凭据；`.env` 已被忽略，请勿提交。

## License

CC0 1.0 Universal（见 [LICENSE](LICENSE)）
