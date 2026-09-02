"""Written-report validation and evidence-safe fallback coverage."""

from __future__ import annotations

import unittest

from app.agents.reporter import SECTION_IDS, WrittenReport, _validate_model_report, render_markdown


class ReporterTests(unittest.TestCase):
    def test_fallback_preserves_fact_problem_strategy_chain(self) -> None:
        project = {"name": "街区更新", "project_type": "改造", "location": "杭州", "stage": "前期调研", "objective": "判断公共空间机会"}
        insight = {"id": "i1", "category": "site_fact", "title": "入口保留", "content": "场地东侧入口需要保留。"}
        problem = {"id": "p1", "title": "入口与活动冲突", "description": "入口交通可能切割活动空间", "linked_insight_ids": ["i1"], "research_gap": "高峰时段人流"}
        strategy = {"id": "s1", "problem_id": "p1", "name": "分时共享界面", "actions": ["划分通行带与停留带"], "preconditions": ["核实高峰流线"], "tradeoffs": ["减少部分连续活动面积"], "validation_items": ["工作日与周末定点观察"]}
        content = render_markdown(project, [insight], [problem], [strategy])
        self.assertIn("场地东侧入口需要保留", content)
        self.assertIn("入口与活动冲突", content)
        self.assertIn("分时共享界面", content)
        self.assertIn("工作日与周末定点观察", content)

    def test_model_report_requires_complete_allowlisted_coverage(self) -> None:
        sections = [
            {"id": section_id, "title": f"章节{index}", "content": chr(0x4E00 + index) * 245}
            for index, section_id in enumerate(SECTION_IDS, start=1)
        ]
        report = WrittenReport.model_validate({
            "title": "建筑调研报告",
            "sections": sections,
            "used_insight_ids": ["i1"],
            "used_problem_ids": ["p1"],
            "used_strategy_ids": ["s1"],
            "character_count": 1470,
        })
        _validate_model_report(report, {"i1"}, {"p1"}, {"s1"})
        report.used_strategy_ids = []
        with self.assertRaisesRegex(ValueError, "every selected strategy"):
            _validate_model_report(report, {"i1"}, {"p1"}, {"s1"})


if __name__ == "__main__":
    unittest.main()
