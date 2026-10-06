"""Coverage tests for HTMLGenerator.generate branches."""

from src.models import ExecutionResult, IterationResult, TokenUsage
from src.reporting.html_generator import HTMLGenerator


def _result(problem_id="p1", strategy="vanilla", with_iterations=False):
    iterations = []
    if with_iterations:
        for i in (1, 2):
            iterations.append(
                IterationResult(
                    iteration=i,
                    code="print(1)",
                    llm_response=None,
                    status="success",
                    llm_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                )
            )
    return ExecutionResult(
        problem_id=problem_id,
        strategy=strategy,
        generated_code="print(1)",
        status="success",
        iterations=iterations,
        llm_traces=[
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "pricing_metadata": {
                    "model": "test-model",
                    "total_cost": 0.02,
                    "usage_known": True,
                    "pricing_known": True,
                },
            }
        ],
    )


def _metrics(pricing_metadata=None):
    return {
        "vanilla": {
            "total_problems": 1,
            "solved_problems": 1,
            "success_rate": 1.0,
            "avg_tokens_per_problem": 15,
            "estimated_cost_usd": 0.02,
            "pricing_metadata": pricing_metadata,
            "by_difficulty": {"easy": {"solved": 1, "total": 1, "success_rate": 1.0}},
        }
    }


def _problems():
    return [
        {
            "problem_id": "p1",
            "title": "P1",
            "difficulty": "easy",
            "tags": ["dp", "array"],
        }
    ]


class TestGeneratePricingSources:
    def test_known_pricing_variant(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics({"has_actual_pricing": True, "unknown_usage": False}),
            {"vanilla": [_result()]},
            str(out),
            include_charts=False,
        )
        content = out.read_text(encoding="utf-8")
        assert "自定义配置/内置定价" in content

    def test_partial_unknown_variant(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics({"has_actual_pricing": True, "unknown_usage": True}),
            {"vanilla": [_result()]},
            str(out),
            include_charts=False,
        )
        assert "部分未知" in out.read_text(encoding="utf-8")

    def test_unknown_pricing_variant(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics({"has_actual_pricing": False, "unknown_pricing": True}),
            {"vanilla": [_result()]},
            str(out),
            include_charts=False,
        )
        assert "未知（模型定价未配置）" in out.read_text(encoding="utf-8")

    def test_missing_pricing_metadata_variant(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(None),
            {"vanilla": [_result()]},
            str(out),
            include_charts=False,
        )
        content = out.read_text(encoding="utf-8")
        assert "当前配置（历史数据不可用）" in content


class TestGenerateChartBranches:
    def test_charts_embedded_with_iterations(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(),
            {"vanilla": [_result(with_iterations=True)]},
            str(out),
            include_charts=True,
        )
        content = out.read_text(encoding="utf-8")
        assert "Token Consumption and Cost" in content
        assert "Iteration Distribution" in content

    def test_chart_none_branches_render_placeholders(self, tmp_path, monkeypatch):
        from src.reporting import html_generator as hg

        monkeypatch.setattr(
            hg.ChartGenerator, "generate_token_chart", staticmethod(lambda *a, **k: None)
        )
        monkeypatch.setattr(
            hg.ChartGenerator,
            "generate_iteration_distribution",
            staticmethod(lambda r: None),
        )
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(),
            {"vanilla": [_result(with_iterations=True)]},
            str(out),
            include_charts=True,
        )
        content = out.read_text(encoding="utf-8")
        assert "No multi-round data available" in content

    def test_capability_radar_rendered_with_problems(self, tmp_path):
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(),
            {"vanilla": [_result()]},
            str(out),
            include_charts=True,
            problems=_problems(),
        )
        content = out.read_text(encoding="utf-8")
        assert "Model Capability Radar" in content
        assert "Capability Analysis: vanilla" in content

    def test_capability_radar_exception_renders_error_card(self, tmp_path, monkeypatch):
        from src.reporting import html_generator as hg

        monkeypatch.setattr(
            hg.ChartGenerator,
            "generate_capability_radar",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("radar down"))),
        )
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(),
            {"vanilla": [_result()]},
            str(out),
            include_charts=True,
            problems=_problems(),
        )
        content = out.read_text(encoding="utf-8")
        assert "Capability Radar Section" in content
        assert "radar down" in content

    def test_capability_radar_none_branch(self, tmp_path, monkeypatch):
        from src.reporting import html_generator as hg

        monkeypatch.setattr(
            hg.ChartGenerator, "generate_capability_radar", staticmethod(lambda *a, **k: None)
        )
        out = tmp_path / "r.html"
        HTMLGenerator.generate(
            _metrics(),
            {"vanilla": [_result()]},
            str(out),
            include_charts=True,
            problems=_problems(),
        )
        content = out.read_text(encoding="utf-8")
        assert "Model Capability Radar" not in content
