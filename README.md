# 筑析 AI — 建筑场地调研与方案汇报助手

> 面向建筑设计前期的多 Agent 助手：把分散的任务书、调研笔记、场地照片转化为 **带来源、可确认的洞察 → 结构化问题 → 可选策略 → Markdown 汇报大纲**。本地单用户演示，开箱可跑。

---

## 📌 项目简介

建筑设计前期资料分散、事实与判断混写、汇报逻辑难建立。**筑析**不替人做设计，而是解决三件事：

1. **提取** — 从 TXT / MD / PDF / PNG / JPG 中抽取场地事实、设计约束、用户诉求、信息缺口，全部绑定原文来源
2. **诊断** — 基于已确认事实生成问题卡，证据不足则标为待验证假设
3. **推演与汇报** — 生成 2–3 个带前提/取舍/验证项的策略卡，用户勾选后导出 `现状—问题—策略` 结构的 Markdown 大纲

明确边界：仅用于课程 / 公开 / 脱敏资料，**不是**建筑规范、消防、结构或日照审查工具。

---

## 🧱 技术栈与框架

| 层 | 技术 | 说明 |
|---|---|---|
| **语言** | Python 3.11 | 唯一运行时 |
| **Web 框架** | FastAPI + Uvicorn | REST API + 静态页托管 |
| **数据校验** | Pydantic | 请求/响应 Schema |
| **多 Agent 编排** | LangGraph | 四阶段顺序工作流（受控执行，模型仅输出 JSON） |
| **大模型** | DeepSeek `deepseek-chat` (文本) / `deepseek-v4-flash-vision-exp` (图片) | 通过 OpenAI 兼容接口调用 |
| **RAG 检索** | ChromaDB + Ollama Embedding (`qwen3-embedding:0.6b` 1024维) | 本地向量库，按 `project_id` 隔离；不可用时降级为 SQLite 原文检索 |
| **数据库** | SQLite (`data/zhuxi_mvp.sqlite3`) | 项目、文档、切片、洞察/问题/策略/导出 |
| **文件解析** | pypdf / python-docx / python-multipart | 文本与图片上传、切块、来源定位 |
| **前端** | 原生 HTML / CSS / JS (`app/static/`) | 极简单页工作台，无前端框架 |
| **其他** | python-dotenv | 本地 `.env` 密钥管理 |

### 架构图

```
用户 → 极简 HTML 工作台 → FastAPI
                          ├── 文件解析 (PDF/TXT/MD + 图片保存)
                          ├── 本地 Embedding (Ollama) → ChromaDB
                          ├── SQLite (项目/卡片/会话)
                          └── LangGraph 四阶段 → DeepSeek
                                               └── output/*.md
```

### 四 Agent 职责

```
资料提取 Agent → 待确认洞察卡 → [人工确认/驳回]
       ↓ 已确认事实
场地诊断 Agent → 问题卡 (关联已确认事实 / 标假设)
       ↓
策略推演 Agent → 2-3 策略卡 (前提/取舍/验证项)
       ↓ [人工勾选]
汇报生成 Agent → Markdown 大纲 (仅含已确认+已选内容)
```

策略与汇报拆分为两个 Agent：前者做**方案选择**（需人介入），后者做**表达组织**（不新增事实），避免模型在汇报阶段替用户做设计决策。

---

## 📁 目录结构

```
筑析/
├── app/
│   ├── main.py              # FastAPI 入口、静态页、异常处理
│   ├── db.py                # SQLite 建表与连接
│   ├── schemas.py           # Pydantic 模型
│   ├── agents/
│   │   ├── graph.py         # LangGraph 状态图（受控顺序）
│   │   ├── extractor.py     # 资料提取
│   │   ├── diagnostician.py # 场地诊断
│   │   ├── strategist.py    # 策略推演
│   │   └── reporter.py      # 汇报生成
│   ├── services/
│   │   ├── parser.py        # 文本/PDF解析、图片保存
│   │   ├── rag.py           # 切块、embedding、Chroma 检索
│   │   └── repositories.py  # SQLite 读写与门禁校验
│   ├── routes/
│   │   ├── upstream.py      # 项目/文档/洞察
│   │   └── downstream.py    # 问题/策略/导出
│   └── static/              # index.html + CSS/JS
├── fixtures/                # 演示资料 (demo-brief.txt 等)
├── docs/
│   ├── mvp-contract.md      # MVP 合同（表结构/API契约）
│   ├── acceptance.md        # 验收清单
│   └── demo-script.md       # 3 分钟演示台词
├── data/                    # SQLite + Chroma 持久化（不提交）
├── uploads/                 # 原始上传，按 project_id 隔离（不提交）
├── output/                  # 导出 Markdown（不提交）
├── requirements.txt
├── .env.example             # 环境变量模板
└── README.md
```

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.11
- 可选：[Ollama](https://ollama.com/)（本地 RAG 向量检索）

### 2. 安装

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

### 3. 配置（可选）

复制模板后在本地填写，`.env` 已被 `.gitignore` 忽略，**绝不提交**：

```powershell
copy .env.example .env
```

`.env` 示例：

```env
DEEPSEEK_API_KEY=你的本机密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEXT_MODEL=deepseek-chat
DEEPSEEK_VISION_MODEL=

# 本地 RAG（可选）
OLLAMA_EMBED_URL=http://127.0.0.1:11434/api/embed
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_EMBED_TIMEOUT_SECONDS=20
CHROMA_DIR=data/chroma
```

> **无 Key 也可演示**：不创建 `.env` 或留空 `DEEPSEEK_API_KEY` 时，系统进入 `demo_fallback` 降级模式，文本洞察绑定原文片段、图片标记为信息缺口，仍可跑通全闭环。

**本地 RAG 说明**：上传的 TXT/MD/PDF 会切块后经 Ollama 生成 1024 维向量写入 ChromaDB，检索时按 `project_id` 过滤。若 Ollama/Chroma 不可用，上传仍成功（`rag_status: degraded`），检索降级为 `sqlite_raw_chunks`。

### 4. 启动

```powershell
python -m uvicorn app.main:app --reload
```

- 工作台：<http://127.0.0.1:8000/>
- 健康检查：<http://127.0.0.1:8000/health>
- API 文档：<http://127.0.0.1:8000/docs>

---

## 📖 使用说明

### 标准演示闭环（3 分钟）

```
创建项目 → 上传 1-3 份文本 + 1-2 张图片 → 生成带来源洞察
        → 人工确认/修改/驳回 → 生成问题卡 → 勾选问题生成策略 → 勾选策略导出 Markdown
```

**关键门禁**：未确认的洞察不会进入问题/策略/导出；`待确认/待验证` 状态被下游严格拦截。

### 推荐演示资料

- `fixtures/demo-brief.txt` — 脱敏任务书文本
- `fixtures/site-context-illustration.png` — 虚构场地示意图（仅验证图片上传，不作为事实）

### HTTP API 速览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/{id}` | 查询项目 |
| POST | `/api/projects/{id}/documents` | 上传文件 `multipart/form-data: files[]` |
| POST | `/api/projects/{id}/insights:generate` | 生成洞察卡 |
| GET | `/api/projects/{id}/insights` | 列出洞察 |
| PATCH | `/api/insights/{id}` | 更新洞察（标题/内容/分类/审核状态） |
| POST | `/api/projects/{id}/problems:generate` | 生成问题卡 |
| GET | `/api/projects/{id}/problems` | 列出问题 |
| POST | `/api/projects/{id}/strategies:generate` | 按问题生成策略 |
| PATCH | `/api/strategies/{id}` | 勾选/取消策略 |
| POST | `/api/projects/{id}/exports/markdown` | 导出 Markdown |
| GET | `/api/exports/{id}/download` | 下载导出文件 |

失败统一格式：`{"error":{"code":"...","message":"...","details":{}}}`（如 `GATE_BLOCKED`、`VALIDATION_ERROR`）。

---

## 🔧 两种运行模式

| 模式 | 触发条件 | 表现 |
|---|---|---|
| **正常模型模式** | `.env` 中 `DEEPSEEK_API_KEY` 完整 | 调用 DeepSeek 生成结构化卡片，仍需人工确认 |
| **无 Key 降级** | 无 `.env` 或 Key 为空 | 返回 `mode: demo_fallback`，文本卡绑定原文、图片卡为信息缺口，可完成闭环 |

---

## 🧪 验收与文档

- 逐项验收：`docs/acceptance.md`
- 3 分钟演示台词：`docs/demo-script.md`
- MVP 合同（表结构与门禁契约）：`docs/mvp-contract.md`

---

## ⚠️ 注意事项

- 仅本地单用户演示，无登录/多用户/鉴权
- `uploads/`、`output/`、`data/` 仅本地存储，不提交 Git
- 密钥只从环境变量读取，不写入源码/前端/日志
- 图片单张不推导面积/限高/消防等结论，看不清的文字标为 `pending` / `needs_verification`

---

## 📄 License

仅作课程与演示用途。
