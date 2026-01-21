import pytest

from services.agent_orchestrator import ReflectionOrchestrator


def test_planner_builds_prompt_with_fk_hints():
    orch = ReflectionOrchestrator()
    prompt, hints = orch._build_plan(
        question="List sales by store",
        context="FK: [dbo].[sales].[store_id] -> [dbo].[stores].[id]",
        error=None,
        last_sql=None,
    )
    assert "T-SQL" in prompt
    assert "sales" in prompt.lower()
    assert "stores" in prompt.lower()
    assert "FK" in prompt or hints


@pytest.mark.parametrize("sql", [
    "select top 5 * from [dbo].[table]",
    "SELECT * FROM [dbo].[table]",
])
def test_critic_accepts_valid_tsql(sql):
    orch = ReflectionOrchestrator()
    repaired = orch._critic_and_correct(sql, plan_prompt=sql, fk_hints="", inference_mode="local", last_error=None)
    assert isinstance(repaired, str) and repaired.strip()
