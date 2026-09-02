"""End-to-end contracts for Stage C problem selection and strategies."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.routes import downstream


class StageCApiTests(unittest.TestCase):
    def test_selection_single_choice_and_custom_strategy_crud(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            generated = [
                {"name": "策略一", "actions": ["行动一"], "preconditions": ["前提一"], "tradeoffs": ["取舍一"], "validation_items": ["验证一"]},
                {"name": "策略二", "actions": ["行动二"], "preconditions": ["前提二"], "tradeoffs": ["取舍二"], "validation_items": ["验证二"]},
            ]
            with patch.object(db, "DATABASE_PATH", root / "test.sqlite3"), patch.object(db, "DATA_DIR", root / "data"), patch.object(db, "UPLOADS_DIR", root / "uploads"), patch.object(db, "OUTPUT_DIR", root / "output"), patch.object(db, "STATIC_DIR", root / "static"), patch.object(downstream.graph, "run_strategies", return_value=(generated, "demo_fallback", "本地测试策略")):
                with TestClient(app) as client:
                    project_id = client.post("/api/projects", json={"name": "阶段 C 接口项目"}).json()["id"]
                    # Server-side setup mirrors the output of the problem generator.
                    from app.services import repositories

                    problem = repositories.create_problem(project_id, "待选择问题", "问题描述", ["confirmed-insight"], "confirmed", "high", "无", status="ready")
                    blocked = client.post(f"/api/projects/{project_id}/strategies:generate", json={})
                    self.assertEqual(blocked.status_code, 409)
                    self.assertEqual(blocked.json()["error"]["code"], "GATE_BLOCKED")

                    selected_problem = client.patch(f"/api/problems/{problem['id']}", json={"selected": True})
                    self.assertTrue(selected_problem.json()["selected"])
                    # Reload verifies this is SQLite state, not browser-only state.
                    self.assertTrue(client.get(f"/api/projects/{project_id}/problems").json()["problems"][0]["selected"])

                    response = client.post(f"/api/projects/{project_id}/strategies:generate", json={})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["outcomes"][problem["id"]], "created")
                    strategies = response.json()["strategies"]
                    first, second = strategies
                    self.assertTrue(client.patch(f"/api/strategies/{first['id']}", json={"selected": True}).json()["selected"])
                    self.assertTrue(client.patch(f"/api/strategies/{second['id']}", json={"selected": True}).json()["selected"])
                    stored = client.get(f"/api/projects/{project_id}/strategies").json()["strategies"]
                    self.assertEqual(sum(item["selected"] for item in stored if item["problem_id"] == problem["id"]), 1)
                    reused = client.post(f"/api/projects/{project_id}/strategies:generate", json={}).json()
                    self.assertEqual(reused["outcomes"][problem["id"]], "reused")

                    custom_payload = {"name": "现场共创", "actions": ["组织访谈"], "preconditions": ["确定参与者"], "tradeoffs": ["需要协调时间"], "validation_items": ["访谈纪要"]}
                    custom = client.post(f"/api/problems/{problem['id']}/strategies", json=custom_payload)
                    self.assertEqual(custom.status_code, 201)
                    self.assertTrue(custom.json()["is_custom"])
                    edited = client.patch(f"/api/strategies/{custom.json()['id']}", json={"name": "现场共创（调整）"})
                    self.assertEqual(edited.json()["name"], "现场共创（调整）")
                    self.assertTrue(client.delete(f"/api/strategies/{custom.json()['id']}").json()["deleted"])


if __name__ == "__main__":
    unittest.main()
