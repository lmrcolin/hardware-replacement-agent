"""Planning (ADR-014): the LLM proposes which deterministic tools to run; a rule policy proposes
the same when no LLM is available and is the guard that keeps every LLM plan valid.

The planner never decides compatibility, prices or stock: it only orders tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

ToolName = Literal[
    "lookup_part",
    "find_substitutes",
    "search_catalog",
    "relax_requirements",
    "ask_datasheets",
    "compare",
    "ask_customer",
    "finish",
]
TOOLS_DOC: dict[str, str] = {
    "lookup_part": "Identifica en el catálogo la pieza mencionada (estado, precio, stock).",
    "find_substitutes": "Busca sustitutos ACTIVE de la pieza identificada y valida su "
    "compatibilidad con el motor de reglas.",
    "search_catalog": "Busca productos ACTIVE que cumplan los requisitos (sin part number).",
    "relax_requirements": "Si no hubo resultados, prueba quitar UN requisito y dice qué se "
    "podría vender a cambio.",
    "ask_datasheets": "Responde una pregunta técnica con specs extraídas y fragmentos citados "
    "de los datasheets.",
    "compare": "Compara dos productos (specs, precio, stock y si uno sustituye al otro).",
    "ask_customer": "Hace la pregunta que más reduce las opciones cuando falta información.",
    "finish": "Termina: ya hay suficiente para responder.",
}
MAX_STEPS = 6


class AgentAction(BaseModel):
    tool: ToolName
    part_number: str | None = None
    other_part_number: str | None = None


class AgentPlan(BaseModel):
    thought: str = Field(default="", max_length=400)
    steps: list[AgentAction] = Field(default_factory=list, max_length=MAX_STEPS)


@dataclass
class PlanState:
    """What the policy needs to know about the run so far."""

    intent: str
    original: str | None = None  # resolved catalog part
    other: str | None = None  # second product (compare)
    category: bool = False
    requirements: bool = False
    done: list[str] = field(default_factory=list)
    found: int | None = None  # recommendations of the last search
    blocked: bool = False  # lookup needs clarification (ambiguous / suggestion)
    active_original: bool = False


def rule_action(state: PlanState) -> AgentAction:
    """Deterministic policy: the next tool to run. Also the reference the guard checks against."""
    done = state.done
    if state.blocked:
        return AgentAction(tool="finish")
    if "lookup_part" not in done:  # always: the catalog may know the part even without a token
        return AgentAction(tool="lookup_part")
    if "ask_datasheets" in done or "compare" in done:
        return AgentAction(tool="finish")  # the answer is the technical reply / comparison
    if state.intent == "compare" and "compare" not in done and state.original and state.other:
        return AgentAction(
            tool="compare", part_number=state.original, other_part_number=state.other
        )
    if state.intent == "question" and "ask_datasheets" not in done:
        return AgentAction(tool="ask_datasheets", part_number=state.original)
    if state.intent in ("compare", "question"):
        return AgentAction(tool="finish")
    if state.original:
        if state.intent == "status" and state.active_original:
            return AgentAction(tool="finish")
        if "find_substitutes" not in done:
            return AgentAction(tool="find_substitutes", part_number=state.original)
    elif "search_catalog" not in done and "ask_customer" not in done:
        if state.category and state.requirements:
            return AgentAction(tool="search_catalog")
        return AgentAction(tool="ask_customer")
    searched = "find_substitutes" in done or "search_catalog" in done
    if searched and state.found == 0 and "relax_requirements" not in done:
        return AgentAction(tool="relax_requirements")
    return AgentAction(tool="finish")


def check(action: AgentAction, state: PlanState) -> str | None:
    """Why ``action`` cannot run now (None = valid). The orchestrator then uses rule_action."""
    tool, done = action.tool, state.done
    if tool != "finish" and tool in done and tool != "ask_datasheets":
        return f"{tool} ya se ejecutó"
    searched = "find_substitutes" in done or "search_catalog" in done
    answered = "ask_datasheets" in done or "compare" in done
    if tool == "find_substitutes" and (not state.original or searched):
        return "no hay una pieza identificada" if not state.original else "ya se buscó"
    if tool == "search_catalog" and (state.original or searched):
        return "ya hay una pieza identificada o una búsqueda hecha"
    if tool == "search_catalog" and not (state.category and state.requirements):
        return "faltan categoría o requisitos"
    if tool == "ask_customer" and rule_action(state).tool != "ask_customer":
        return "aún no falta información (primero identificar y buscar)"
    if answered and tool in ("find_substitutes", "search_catalog"):
        return "ya hay una respuesta técnica"
    if tool == "relax_requirements" and state.found != 0:
        return "solo aplica cuando la búsqueda no dio resultados"
    if tool == "compare" and not (state.original and state.other):
        return "comparar necesita dos productos identificados"
    if tool == "finish":
        required = rule_action(state)
        if required.tool != "finish":
            return f"falta un paso necesario ({required.tool})"
    return None
