"""Rule policy and guard of the agent planner (ADR-014)."""

from __future__ import annotations

from advisor.agent.planner import AgentAction, PlanState, check, rule_action


def test_policy_runs_lookup_then_substitutes_then_relaxes() -> None:
    state = PlanState(intent="replace")
    assert rule_action(state).tool == "lookup_part"
    state.done, state.original = ["lookup_part"], "A100-SXM4-80GB"
    assert rule_action(state).tool == "find_substitutes"
    state.done.append("find_substitutes")
    state.found = 0
    assert rule_action(state).tool == "relax_requirements"
    state.done.append("relax_requirements")
    assert rule_action(state).tool == "finish"


def test_guard_blocks_finishing_early_and_asking_after_a_search() -> None:
    state = PlanState(intent="replace", original="E810-CQDA2", done=["lookup_part"])
    assert check(AgentAction(tool="finish"), state) == "falta un paso necesario (find_substitutes)"
    state.done.append("find_substitutes")
    state.found = 2
    assert check(AgentAction(tool="ask_customer"), state) is not None
    assert check(AgentAction(tool="search_catalog"), state) is not None
    assert check(AgentAction(tool="finish"), state) is None


def test_questions_and_comparisons_finish_after_answering() -> None:
    state = PlanState(intent="question", done=["lookup_part", "ask_datasheets"])
    assert rule_action(state).tool == "finish"
    compare = PlanState(intent="compare", original="A", other="B", done=["lookup_part"])
    assert rule_action(compare) == AgentAction(
        tool="compare", part_number="A", other_part_number="B"
    )
