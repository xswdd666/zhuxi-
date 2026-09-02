# 筑析 AI｜MVP 验收记录

验收日期：2026-09-01  
验收基线：本机 FastAPI + SQLite；不配置 `DEEPSEEK_API_KEY` 的 `demo_fallback` 模式。  
公开资料：`fixtures/demo-brief.txt`、`fixtures/site-context-illustration.png`（虚构示意图，非事实依据）。

## 实际执行命令

在 `D:\简历\筑析` 执行：

```powershell
$env:DEEPSEEK_API_KEY=''
& 'C:\Users\xsw\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m uvicorn app.main:app --port 8977
```

随后通过 PowerShell `Invoke-RestMethod` 依次调用创建项目、上传两份 fixture、生成洞察、确认两张洞察、生成问题、生成策略、选择策略、导出和下载。完整的可复制操作见 `docs/demo-script.md`。

本次实际验收项目 ID：`8a8ef6aa-ce4e-4634-a336-919acbd6a6fe`  
本次实际导出 ID：`2698760c-e64c-4aed-89dc-95721a9a15ca`

## 06 补充模型验收

以下结果由 06 更新的真实模型联调提供；仅记录模式、模型名和结果，不记录或展示任何 Key：

- [x] 资料提取：`mode=model`。
- [x] 问题生成：`mode=model`。
- [x] 策略生成：`mode=model`。
- [x] 图片观察：`deepseek-v4-flash-vision-exp` 真实调用成功。
- [x] 无 Key 降级闭环：仍通过，接口返回 `mode: "demo_fallback"`，文本闭环未中断。

## 逐项结果

- [x] `python -m uvicorn app.main:app --reload` 可启动；实际以等价的 `--port 8977` 启动，`GET /health` 返回 `{"status":"ok"}`，静态页路由为 `/`。
- [x] 创建了全新项目并上传 TXT 与 PNG。TXT 状态为 `parsed`；PNG 状态为 `saved_image: 未启用 OCR/视觉模型，已保存待人工观察。`。
- [x] 无 Key 下生成 7 张默认 `pending` 的带来源洞察卡，包含 `site_fact`、`design_constraint`、`user_need`、`information_gap` 四类；图片只形成“待人工观察”的信息缺口。
- [x] 未确认时，问题生成、策略生成（传入不存在问题）和 Markdown 导出均返回 `GATE_BLOCKED`。
- [x] 确认两张可追溯洞察后，生成了 `evidence_status: confirmed` 的问题卡，且该卡 `linked_insight_ids` 包含已确认洞察 ID。
- [x] 基于该问题生成策略卡；实际选中的策略均含至少一项 `preconditions`、`tradeoffs` 与 `validation_items`。
- [x] 选择一条策略后成功导出。文件存在于 `output/8a8ef6aa-ce4e-4634-a336-919acbd6a6fe_2698760c-e64c-4aed-89dc-95721a9a15ca.md`，下载接口返回 HTTP 200。
- [x] 导出内容检查：2 张已确认洞察正文均出现；5 张未确认洞察标题均未出现；已选策略出现，未选策略名称均未出现。
- [x] 结束并重新启动验收服务后，`GET /api/projects/8a8ef6aa-ce4e-4634-a336-919acbd6a6fe` 仍返回同一项目，确认 SQLite 数据持久化。
- [x] 本次不配置 Key，洞察、问题和策略接口均返回 `mode: "demo_fallback"`（洞察、问题、策略），文本闭环未中断；06 补充复验后仍通过。
- [x] 没有创建真实 `.env`；`.gitignore` 已忽略 `.env`。代码与文档只出现环境变量名称或占位符，未记录密钥值。

## 已知限制与风险

- DeepSeek 文本、问题、策略与图片观察的真实调用已通过一次联调；网络可用性、模型额度与上游服务变化仍可能影响后续调用。
- 即使图片观察真实调用成功，图片输出仍是待人工审核洞察，不能直接当作项目事实或专业结论。
- 这是本地单用户演示应用。SQLite、文件存储和无认证设计不适用于多人或生产环境。
- 公开 fixture 是演示资料，不能用于专业规范、规划审批或工程决策。
