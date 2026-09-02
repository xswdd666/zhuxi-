"""Stage D report persistence, editing, and saved-Markdown export coverage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.routes import downstream
from app.services import repositories


class StageDApiTests(unittest.TestCase):
    def test_report_uses_admitted_data_can_be_edited_and_exports_saved_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with patch.object(db, "DATABASE_PATH", root / "test.sqlite3"), patch.object(db, "DATA_DIR", root / "data"), patch.object(db, "UPLOADS_DIR", root / "uploads"), patch.object(db, "OUTPUT_DIR", root / "output"), patch.object(db, "STATIC_DIR", root / "static"), patch.object(downstream, "OUTPUT_DIR", root / "output"), patch.object(downstream, "generate_written_report", side_effect=lambda project, insights, problems, strategies: (f"# 测试报告\n\n{insights[0]['content']}", "demo_fallback", "测试降级")):
                with TestClient(app) as client:
                    project_id = client.post("/api/projects", json={"name": "汇报验收项目", "project_type": "改造"}).json()["id"]
                    self.assertEqual(client.post(f"/api/projects/{project_id}/reports:generate").status_code, 409)
                    insight = repositories.create_insight(project_id, "site_fact", "已确认事实", "仅此事实可进入汇报。", [{"document_id": "document", "file_name": "brief.md", "locator": "文本片段 1", "quote": "仅此事实"}], 0.9, "confirmed")
                    problem = repositories.create_problem(project_id, "核心问题", "仅基于确认事实的问题。", [insight["id"]], "confirmed", "high", "继续核验", status="ready")
                    repositories.update_problem_selected(problem["id"], True)
                    repositories.create_strategy(project_id, problem["id"], "已选策略", ["执行行动"], ["具备前提"], ["接受取舍"], ["检查结果"], selected=True)

                    second = repositories.create_problem(project_id, "尚缺策略的问题", "用于验证策略完成门禁。", [insight["id"]], "confirmed", "medium", "补充观察", status="ready")
                    repositories.update_problem_selected(second["id"], True)
                    incomplete = client.post(f"/api/projects/{project_id}/reports:generate")
                    self.assertEqual(incomplete.status_code, 409)
                    self.assertEqual(incomplete.json()["error"]["code"], "STRATEGY_SELECTION_INCOMPLETE")
                    self.assertEqual(incomplete.json()["error"]["details"]["completed_problem_count"], 1)
                    self.assertEqual(incomplete.json()["error"]["details"]["missing_problems"][0]["title"], "尚缺策略的问题")
                    repositories.update_problem_selected(second["id"], False)

                    generated = client.post(f"/api/projects/{project_id}/reports:generate")
                    self.assertEqual(generated.status_code, 200)
                    report = generated.json()["report"]
                    self.assertIn("仅此事实可进入汇报", report["content"])
                    self.assertNotIn("未确认", report["content"])
                    self.assertEqual(client.get(f"/api/projects/{project_id}/report").json()["report"]["id"], report["id"])

                    revised_outline = list(reversed(report["outline"]))
                    edited = client.patch(f"/api/reports/{report['id']}", json={"outline": revised_outline, "content": "# 已编辑汇报\n\n正文已由用户保存。"})
                    self.assertEqual(edited.status_code, 200)
                    exported = client.post(f"/api/reports/{report['id']}/export/markdown")
                    self.assertEqual(exported.status_code, 200)
                    export = exported.json()["export"]
                    self.assertNotIn("path", export)
                    download = client.get(f"/api/exports/{export['id']}/download")
                    self.assertEqual(download.status_code, 200)
                    self.assertIn("正文已由用户保存", download.text)


if __name__ == "__main__":
    unittest.main()
