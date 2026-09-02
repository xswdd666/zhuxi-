# 筑析 Zhuxi — 建筑前期智能决策工作台

> **让每一份场地资料，都成为可追溯、可决策、可汇报的设计依据。**
> 筑析是面向建筑师、规划师与业主方的 AI 协作产品：自动解构任务书与现场资料，沉淀可信场地知识库，推演关键问题与可行策略，一键生成专业汇报大纲。

<p>

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-6B4EFF)
![DeepSeek](https://img.shields.io/badge/DeepSeek-V4-4A90E2)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FF6B35)
![License](https://img.shields.io/badge/License-MIT-green)

</p>

---

## 为什么需要筑析？

建筑前期有三个典型痛点：

- **资料分散难沉淀** — 任务书、调研笔记、会议纪要、现场照片散落在文件夹，关键信息难以快速定位与复用
- **事实与判断混淆** — 拍脑袋的推断被当成场地事实写入方案，后期反复推翻
- **汇报缺少逻辑链** — 从现状到问题再到策略的论证断层，沟通成本极高

**筑析用「提取—确认—诊断—推演—汇报」五步闭环解决它：** 每一条洞察都绑定原文来源，每一个问题都关联已确认事实，每一条策略都说明前提、取舍与验证项，最终导出结构化的 `现状—问题—策略` 汇报。

> 筑析不替代设计判断，而是让判断建立在可信、可追溯的事实之上。

---

## 核心能力

### 1. 全源资料智能提取
支持 **TXT / MD / PDF / PNG / JPG** 一键上传。文本自动切块定位到页码与段落，图片保留原图并生成结构化观察。所有产出分为四类卡片：

- **场地事实** — 可验证的客观信息
- **设计约束** — 法规、红线、限高、退距等边界条件
- **用户诉求** — 业主与使用方的核心需求
- **信息缺口** — 需要补充调研或核实的盲区

每张卡片自带 `文件名 · 定位符 · 原文摘录`，一键溯源，拒绝幻觉。

### 2. 人机协同的确认机制
AI 负责广度，人负责精度。所有洞察默认为 **待确认**，需经人工 **确认 / 修改 / 驳回** 后才进入下游。未确认内容被严格门禁拦截，绝不混入问题分析与汇报，确保知识库的纯净度。

### 3. 场地问题深度诊断
基于已确认事实与 RAG 检索上下文，自动诊断核心矛盾与潜在风险。证据充足的问题直接关联来源，证据不足的则明确标注为 **待验证假设** 并给出研究缺口，不把猜测包装成结论。

### 4. 多路径策略推演
针对已选问题，并行推演 **2–3 条差异化策略**，每条策略包含：

- **核心举措** — 具体可执行的行动
- **实施前提** — 需要满足的条件
- **利弊权衡** — 坦诚呈现取舍
- **验证清单** — 下一步必须核实的事项

策略供你选择，而非替你决策。

### 5. 一键生成专业汇报
勾选心仪策略，一键导出可直接用于内外部汇报的 **Markdown 大纲**。内容仅包含已确认洞察、已选问题与已选策略，结构清晰、可二次编辑，输出到本地 `output/` 即取即用。

---

## 产品工作流

```
创建项目 → 上传资料 → AI 提取洞察 → 人工确认 → AI 诊断问题 → 选择问题推演策略 → 勾选策略生成汇报
```

| 步骤 | 角色 | 产出 |
|---|---|---|
| 资料提取 | AI + 溯源 | 带来源的四类洞察卡 |
| 人工确认 | 人 | 可信知识库 |
| 场地诊断 | AI | 关联事实的问题卡 |
| 策略推演 | AI | 含前提/取舍/验证项的策略卡 |
| 汇报生成 | AI + 人选 | Markdown 专业大纲 |

---

## 技术栈与框架

筑析以 **本地优先、隐私可控** 为设计原则，所有数据与文件默认落盘本地。

| 层级 | 技术选型 | 职责 |
|---|---|---|
| **运行时** | Python 3.11 | 核心语言 |
| **Web 服务** | FastAPI + Uvicorn | 高性能异步 API 与静态工作台托管 |
| **数据校验** | Pydantic | 全链路强类型契约 |
| **Agent 编排** | LangGraph | 四阶段顺序工作流，受控执行、模型仅输出结构化 JSON |
| **大模型** | DeepSeek `deepseek-chat` / `deepseek-v4-flash-vision-exp` | 文本理解与图像结构化观察（OpenAI 兼容接口） |
| **知识检索** | ChromaDB + Ollama `qwen3-embedding:0.6b` (1024维) | 本地向量化与项目级隔离检索，离线可用，自动降级至原文检索 |
| **持久化** | SQLite | 项目、文档、切片、卡片、导出一体化存储 |
| **文档解析** | pypdf / python-docx / python-multipart | 多格式文本抽取与来源定位 |
| **前端** | 原生 HTML / CSS / JavaScript | 轻量、零框架依赖的专业工作台 |
| **配置管理** | python-dotenv | 环境隔离的密钥管理 |

### 系统架构

```
                ┌─────────────────────┐
                │   筑析工作台 (Web)   │
                └─────────┬───────────┘
                          │ HTTP
                ┌─────────▼───────────┐
                │  FastAPI 服务层      │
                └──┬───┬───┬──────────┘
                   │   │   │
        ┌──────────▼┐ ┌▼──▼────────┐ ┌──────────────┐
        │ 文件解析   │ │ LangGraph  │ │  SQLite      │
        │ PDF/TXT/  │ │ 四 Agent   │ │ 项目/卡片    │
        │ MD/图像   │ │ 工作流     │ │ 会话/导出    │
        └─────┬─────┘ └──┬──┬──────┘ └──────────────┘
              │          │  │
     ┌────────▼────┐ ┌───▼──▼────┐
     │ Ollama      │ │ DeepSeek  │
     │ Embedding   │ │ 大模型    │
     └──────┬──────┘ └───────────┘
            │
     ┌──────▼──────┐
     │ ChromaDB    │
     │ 向量知识库   │
     └─────────────┘
```

### 四 Agent 协作模型

```
资料提取 Agent ──► 待确认洞察 ──► [人工确认/驳回]
                         │
                  已确认事实库
                         │
场地诊断 Agent ──► 问题卡 (关联事实 / 标注假设)
                         │
策略推演 Agent ──► 策略卡 (前提 · 取舍 · 验证项)
                         │
                  [人工勾选策略]
                         │
汇报生成 Agent ──► Markdown 大纲 (仅已确认+已选)
```

策略与汇报分属两个独立 Agent：前者负责**发散与权衡**，后者负责**收敛与表达**，职责清晰，防止模型在汇报阶段擅自新增决策。

---

## 快速开始

### 环境要求

- Python 3.11
- 可选：[Ollama](https://ollama.com/) — 启用本地向量检索，获得更精准的上下文召回

### 安装

```powershell
# Windows PowerShell
python --version  # 需 3.11.x
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 配置

```powershell
copy .env.example .env
```

编辑 `.env`（已加入 `.gitignore`，不会被提交）：

```env
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEXT_MODEL=deepseek-chat
DEEPSEEK_VISION_MODEL=

# 本地知识库（可选，推荐开启）
OLLAMA_EMBED_URL=http://127.0.0.1:11434/api/embed
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_EMBED_TIMEOUT_SECONDS=20
CHROMA_DIR=data/chroma
```

> 未配置 Key 时自动进入离线解析模式：文本洞察直接绑定原文切片，图片标记为待观察项，核心流程不受影响。

### 启动

```powershell
python -m uvicorn app.main:app --reload
```

| 入口 | 地址 |
|---|---|
| 工作台 | http://127.0.0.1:8000/ |
| 健康检查 | http://127.0.0.1:8000/health |
| API 文档 | http://127.0.0.1:8000/docs |

---

## 使用指南

### 推荐工作流

1. **创建项目** — 填写项目名称、类型与简介
2. **上传资料** — 拖拽 1–3 份文本与 1–2 张现场图片
3. **生成洞察** — 一键提取，逐条核对来源后确认
4. **诊断问题** — 基于已确认事实生成问题卡
5. **推演策略** — 勾选关键问题，获得多路径策略
6. **导出汇报** — 勾选策略，一键下载 Markdown

> 示例资料：`fixtures/demo-brief.txt` 与 `fixtures/site-context-illustration.png` 可直接用于体验完整链路。

### API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 查询项目 |
| POST | `/api/projects/{id}/documents` | 上传文件 `files[]` |
| POST | `/api/projects/{id}/insights:generate` | 生成洞察卡 |
| GET | `/api/projects/{id}/insights` | 列出洞察 |
| PATCH | `/api/insights/{id}` | 更新洞察 |
| POST | `/api/projects/{id}/problems:generate` | 生成问题卡 |
| GET | `/api/projects/{id}/problems` | 列出问题 |
| POST | `/api/projects/{id}/strategies:generate` | 生成策略卡 |
| PATCH | `/api/strategies/{id}` | 勾选/取消策略 |
| POST | `/api/projects/{id}/exports/markdown` | 导出 Markdown |
| GET | `/api/exports/{id}/download` | 下载文件 |

统一错误格式：`{"error": {"code": "...", "message": "...", "details": {}}}`

---

## 目录结构

```
筑析/
├── app/
│   ├── main.py              # FastAPI 入口与路由
│   ├── db.py                # SQLite 建表与连接
│   ├── schemas.py           # Pydantic 契约
│   ├── agents/              # 四 Agent：extractor / diagnostician / strategist / reporter
│   ├── services/            # parser / rag / repositories
│   ├── routes/              # upstream / downstream
│   └── static/              # 工作台前端
├── fixtures/                # 示例资料
├── docs/                    # 产品与接口文档
├── data/                    # 本地数据库与向量库（不提交）
├── uploads/                 # 原始文件（按项目隔离，不提交）
├── output/                  # 导出汇报（不提交）
├── requirements.txt
├── .env.example
└── README.md
```

---

## 设计理念

- **可追溯** — 每一条结论都能回到原文，拒绝不可验证的幻觉
- **可管控** — 人在回路，关键节点由人确认，AI 不越权决策
- **可落地** — 策略必带前提、代价与验证项，不给空洞口号
- **隐私优先** — 本地存储、本地检索，核心资料不出本机

---

## License

MIT
