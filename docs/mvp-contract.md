# 筑析 AI｜一日 MVP 合同

目标：当天跑通“创建项目 → 上传文本/图片 → 带来源洞察并确认 → 问题 → 策略并选择 → Markdown 导出”。仅限本地单用户演示，不作专业规范审查。

## 1. 固定目录与职责

```text
app/
  main.py              # FastAPI 入口、路由、静态页挂载
  db.py                # SQLite 建表与连接
  schemas.py           # Pydantic 请求/响应模型
  agents/graph.py      # LangGraph；不可用时按相同顺序调用受控函数
  agents/*.py          # extractor / diagnostician / strategist / reporter
  services/parser.py   # 文本提取、图片保存与来源片段
  services/repositories.py # SQLite 读写与门禁校验
  static/index.html    # 唯一前端页面
uploads/               # 原始上传，按 project_id 隔离
output/                # 导出的 Markdown
docs/mvp-contract.md   # 本合同
```

不引入登录、多用户、JWT、前端框架、Docker、PostgreSQL、复杂 OCR、CAD/BIM、外网搜索或生产级重构。`本地 uploads/output` 是唯一文件存储。

## 2. SQLite 最小表

```text
projects(id PK, name, project_type, description, created_at)
documents(id PK, project_id FK, file_name, file_type, path, parse_status, created_at)
source_chunks(id PK, document_id FK, locator, content, source_type)
insight_cards(id PK, project_id FK, category, title, content, sources_json,
              confidence, review_status, original_ai_json, updated_at)
problem_cards(id PK, project_id FK, title, description, linked_insight_ids_json,
              evidence_status, priority, research_gap, status)
strategy_cards(id PK, project_id FK, problem_id FK, name, actions_json,
               preconditions_json, tradeoffs_json, validation_items_json, selected)
exports(id PK, project_id FK, path, created_at)
```

`locator` 为页码、段落号或图片描述位置。`sources_json` 至少含 `document_id,file_name,locator,quote`；缺失来源不得作为事实保存。

## 3. HTTP API（JSON，上传除外）

成功响应字段以各资源 JSON Schema 为准；失败一律：

```json
{"error":{"code":"VALIDATION_ERROR","message":"可读错误说明","details":{}}}
```

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/api/projects` | `{name,project_type?,description?}` | `Project` |
| GET | `/api/projects/{project_id}` | — | `Project` |
| POST | `/api/projects/{project_id}/documents` | `multipart/form-data: files[]` | `{documents:[Document]}` |
| POST | `/api/projects/{project_id}/insights:generate` | `{}` | `{insights:[Insight]}` |
| GET | `/api/projects/{project_id}/insights` | — | `{insights:[Insight]}` |
| PATCH | `/api/insights/{id}` | `{title?,content?,category?,review_status}` | `Insight` |
| POST | `/api/projects/{project_id}/problems:generate` | `{}` | `{problems:[Problem]}` |
| GET | `/api/projects/{project_id}/problems` | — | `{problems:[Problem]}` |
| POST | `/api/projects/{project_id}/strategies:generate` | `{problem_ids:[string]}` | `{strategies:[Strategy]}` |
| PATCH | `/api/strategies/{id}` | `{selected:boolean}` | `Strategy` |
| POST | `/api/projects/{project_id}/exports/markdown` | `{}` | `{export:MarkdownExport}` |
| GET | `/api/exports/{export_id}/download` | — | `text/markdown` 文件 |

常用错误码：`NOT_FOUND`、`VALIDATION_ERROR`、`GATE_BLOCKED`、`PARSE_FAILED`、`MODEL_UNAVAILABLE`、`INTERNAL_ERROR`。静态页为 `GET /`。

## 4. 状态机与门禁

```text
Insight: pending → confirmed | edited | rejected | needs_verification
Problem: draft → ready | rejected
Strategy: draft → selected | unselected
Export: 仅在门禁通过后生成
```

- `pending`、`edited`、`needs_verification` 都不是已确认洞察；仅 `confirmed` 可进入问题、策略、正式大纲。
- 洞察若没有可定位的来源，只能是信息缺口/待验证项，不能作为事实或约束。
- 每个问题必须引用至少一张 `confirmed` 洞察；否则 `evidence_status="hypothesis"`，并写明待验证项。不能伪装为事实。
- 策略必须含 `preconditions`、`tradeoffs`、`validation_items`，且关联问题。
- 导出仅使用：已确认洞察、问题及其关联证据、`selected=true` 的策略。不得引入新事实或未选策略；任一条件不满足返回 `GATE_BLOCKED`。

## 5. 最小资源 JSON Schema

以下是实现与模型输出的最小字段契约（所有 `id` 为字符串）。

```json
{
  "Insight": {
    "id":"string", "category":"site_fact|design_constraint|user_need|information_gap",
    "title":"string", "content":"string", "sources":[{"document_id":"string","file_name":"string","locator":"string","quote":"string"}],
    "confidence":0.0, "review_status":"pending|confirmed|edited|rejected|needs_verification"
  },
  "Problem": {
    "id":"string", "title":"string", "description":"string",
    "linked_insight_ids":["string"], "evidence_status":"confirmed|hypothesis",
    "priority":"low|medium|high", "research_gap":"string", "status":"draft|ready|rejected"
  },
  "Strategy": {
    "id":"string", "problem_id":"string", "name":"string", "actions":["string"],
    "preconditions":["string"], "tradeoffs":["string"], "validation_items":["string"], "selected":false
  },
  "MarkdownExport": {
    "id":"string", "project_id":"string", "path":"string", "filename":"string",
    "content":"string", "created_at":"ISO-8601 string"
  }
}
```

## 6. DeepSeek 与无 Key 降级

- 正常：仅后端从 `DEEPSEEK_API_KEY` 读取 Key；文本/图片模型返回上述 JSON，先校验、再保存。Key 不得写入代码、日志、Git、响应或前端。
- 无 Key 或调用失败：请求仍返回可演示的确定性样例卡（来源只引用已上传文本片段；图片仅生成“需人工观察”的信息缺口），并携带 `mode:"demo_fallback"` 与可读提示。无上传资料时返回 `MODEL_UNAVAILABLE`，不能伪造来源。
- 降级数据同样受状态机和所有门禁约束。

## 7. 演示验收

- [ ] `python -m uvicorn app.main:app --reload` 后打开 `http://127.0.0.1:8000/`。
- [ ] 创建项目，上传一份 TXT/MD 和一张 PNG/JPG；文件均显示解析/保存结果。
- [ ] 生成四类带来源、默认 `pending` 的洞察卡；无来源项明确为信息缺口或待验证。
- [ ] 未确认时调用问题、策略或导出均返回 `GATE_BLOCKED`。
- [ ] 确认至少两张可追溯洞察，生成关联这些洞察的问题卡。
- [ ] 基于问题生成含前提、取舍、待验证项的策略卡，选择至少一条。
- [ ] 导出 Markdown；正文只含确认洞察和已选策略，且存在于 `output/` 并可下载。
- [ ] 删除/遮挡 `.env` 后重复主流程，页面明确显示 `demo_fallback`，闭环仍可演示。

### 最小演示资料

保存为 `demo-brief.txt`（任意公开或脱敏内容）：

```text
项目：社区活动中心改造
场地：东侧临城市支路，主要入口位于南侧。
约束：现状北侧保留两层建筑；新建部分高度不超过 24 米。
诉求：为儿童与老年人提供可共享的日间活动空间。
缺口：未提供高峰时段人车流量与停车数据。
```

另备一张公开/脱敏 `site.jpg`；图片不可见信息不得被当作事实。
