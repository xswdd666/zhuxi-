"""Stage E fresh-project regression: gates, recovery, isolation, and fallback."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.routes import downstream
from app.services import parser, rag, repositories


class StageEAcceptanceTests(unittest.TestCase):
    def test_full_fresh_project_flow_recovers_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with patch.object(db, "DATABASE_PATH", root / "acceptance.sqlite3"), patch.object(db, "DATA_DIR", root / "data"), patch.object(db, "UPLOADS_DIR", root / "uploads"), patch.object(db, "OUTPUT_DIR", root / "output"), patch.object(db, "STATIC_DIR", root / "static"), patch.object(parser, "UPLOADS_DIR", root / "uploads"), patch.object(downstream, "OUTPUT_DIR", root / "output"), patch.object(downstream, "generate_written_report", side_effect=lambda project, insights, problems, strategies: (f"# 测试报告\n\n{insights[0]['content']}", "demo_fallback", "测试降级")), patch.object(rag, "index_project_chunks", return_value={"rag_status": "degraded", "indexed_count": 0, "reason": "Ollama embedding unavailable"}), patch.object(rag, "delete_document_vectors", return_value={"rag_status": "degraded"}):
                with TestClient(app) as client:
                    project_id = client.post("/api/projects", json={"name": "阶段 E 新项目"}).json()["id"]
                    client.patch(f"/api/projects/{project_id}", json={"location": "杭州", "stage": "前期资料分析", "objective": "全流程验收", "tags": ["验收"]})
                    uploaded = client.post(f"/api/projects/{project_id}/documents", files=[("files", ("brief.txt", "场地入口需要保留；使用者需要活动空间。", "text/plain")), ("files", ("site.png", b"not-a-real-image", "image/png"))])
                    self.assertEqual(uploaded.status_code, 200)
                    self.assertEqual(uploaded.json()["rag_status"], "degraded")
                    self.assertEqual(len(client.get(f"/api/projects/{project_id}/documents").json()["documents"]), 2)

                    confirmed = repositories.create_insight(project_id, "site_fact", "确认事实", "确认内容进入汇报。", [{"document_id": "doc", "file_name": "brief.txt", "locator": "文本片段 1", "quote": "场地入口"}], 0.9, "confirmed")
                    repositories.create_insight(project_id, "information_gap", "未确认缺口", "这段文字不能进入正式汇报。", [{"document_id": "doc", "file_name": "brief.txt", "locator": "文本片段 1", "quote": "活动空间"}], 0.5, "needs_verification")
                    problem = repositories.create_problem(project_id, "核心问题", "基于确认事实的问题。", [confirmed["id"]], "confirmed", "high", "现场核验", status="ready")
                    client.patch(f"/api/problems/{problem['id']}", json={"selected": True})
                    strategy = repositories.create_strategy(project_id, problem["id"], "选中策略", ["执行"], ["前提"], ["取舍"], ["验证"], selected=True)
                    generated = client.post(f"/api/projects/{project_id}/reports:generate")
                    self.assertEqual(generated.status_code, 200)
                    report = generated.json()["report"]
                    self.assertIn("确认内容进入汇报", report["content"])
                    self.assertNotIn("不能进入正式汇报", report["content"])
                    export = client.post(f"/api/reports/{report['id']}/export/markdown").json()["export"]
                    self.assertIn("确认内容进入汇报", client.get(f"/api/exports/{export['id']}/download").text)

                # A new application lifespan must restore all persisted state.
                with TestClient(app) as restarted:
                    self.assertEqual(restarted.get(f"/api/projects/{project_id}").json()["tags"], ["验收"])
                    self.assertTrue(restarted.get(f"/api/projects/{project_id}/problems").json()["problems"][0]["selected"])
                    stored_strategy = restarted.get(f"/api/projects/{project_id}/strategies").json()["strategies"]
                    self.assertTrue(any(item["id"] == strategy["id"] and item["selected"] for item in stored_strategy))
                    self.assertEqual(restarted.get(f"/api/projects/{project_id}/report").json()["report"]["id"], report["id"])

    def test_rag_fallback_is_project_isolated(self) -> None:
        with patch("app.services.repositories.list_source_chunks") as chunks, patch.object(rag, "_embed", side_effect=rag.RagUnavailable("offline")):
            chunks.return_value = [{"content": "only project A", "file_name": "a.md", "locator": "1", "document_id": "a", "source_type": "text"}]
            result = rag.retrieve_project_context("project-a", "query")
        self.assertEqual(result["retrieval_source"], "sqlite_raw_chunks")
        self.assertEqual(result["results"][0]["document_id"], "a")


if __name__ == "__main__":
    unittest.main()
