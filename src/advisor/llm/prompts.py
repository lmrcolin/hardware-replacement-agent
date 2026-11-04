"""Prompts for NLU (query → ParsedQuery JSON) and NLG (rephrase a verified draft).

Both prompts embed their payload between markers so the deterministic TemplateClient can recover it
without any model.
"""

from __future__ import annotations

import json
import re

from advisor.models import ParsedQuery

QUERY_OPEN, QUERY_CLOSE = "<<<CONSULTA", "CONSULTA>>>"
DRAFT_OPEN, DRAFT_CLOSE = "<<<BORRADOR", "BORRADOR>>>"
PLAN_OPEN, PLAN_CLOSE = "<<<SITUACION", "SITUACION>>>"


def _between(text: str, start: str, end: str) -> str:
    m = re.search(rf"{re.escape(start)}\n(.*)\n{re.escape(end)}", text, re.S)
    if not m:
        raise ValueError(f"prompt without {start} … {end} block")
    return m.group(1)


def build_nlu_prompt(text: str, allowed_keys: dict[str, list[str]]) -> str:
    keys = json.dumps(allowed_keys, ensure_ascii=False)
    schema = json.dumps(ParsedQuery.model_json_schema(), ensure_ascii=False)
    return (
        "Eres un analizador de consultas de reemplazo de hardware. Devuelve SOLO un JSON válido "
        "y compacto con el esquema indicado; omite los campos vacíos o con su valor por defecto.\n"
        "Reglas:\n"
        "- intent: replace (busca sustituto), find (busca producto por requisitos), status "
        "(pregunta estado/precio/stock) u other.\n"
        "- part_numbers: códigos tal como aparecen en la consulta; no los completes ni corrijas.\n"
        "- category: una de CPU, DAQ, FPGA, GPU, Memory, Microcontroller, Network, Power, "
        "Sensor, Storage, o null.\n"
        f"- requirements: solo con estas claves por categoría (clave: unidad): {keys}. "
        "Operadores GTE, LTE, EQ, IN, HAS. Para cifras de capacidad (velocidad, memoria, "
        "canales, resolución…) usa GTE (al menos), nunca EQ. "
        'Usa HAS con value "*" si piden la capacidad sin '
        "detalle (p. ej. 'soporte RDMA'). origin = QUERY. Usa solo valores que aparezcan "
        "literalmente en la consulta; nunca inventes cifras.\n"
        "- needs_clarification = true (con clarification_question) si no hay part number ni "
        "categoría.\n"
        f"Esquema JSON: {schema}\n"
        f"{QUERY_OPEN}\n{text}\n{QUERY_CLOSE}"
    )


def extract_query(prompt: str) -> str:
    """The customer text inside an NLU prompt; a plain string is taken as the query itself."""
    return _between(prompt, QUERY_OPEN, QUERY_CLOSE) if QUERY_OPEN in prompt else prompt


def build_nlg_prompt(draft: str) -> str:
    return (
        "Reescribe el borrador en español claro y profesional para un cliente industrial, en "
        "máximo 110 palabras: la interfaz ya muestra tarjetas con todos los detalles, así que "
        "resume lo esencial (estado de la pieza, opción recomendada con precio y unidades, la "
        "condición principal). Conserva el orden de las recomendaciones. NO añadas, cambies ni "
        "redondees cifras, precios, unidades ni part numbers; no añadas productos ni "
        "afirmaciones técnicas que no "
        "estén en el borrador. Devuelve solo el texto final.\n"
        f"{DRAFT_OPEN}\n{draft}\n{DRAFT_CLOSE}"
    )


def extract_draft(prompt: str) -> str:
    return _between(prompt, DRAFT_OPEN, DRAFT_CLOSE)


def build_planner_prompt(situation: str, tools: dict[str, str], schema: dict[str, object]) -> str:
    """Ask for the ordered tool calls that answer the customer (ReAct-style plan, ADR-014)."""
    catalog = "\n".join(f"- {name}: {doc}" for name, doc in tools.items())
    return (
        "Eres el planificador de un agente de reemplazo de hardware. Decide qué herramientas "
        "ejecutar y en qué orden para atender al cliente. Las herramientas son deterministas: "
        "tú no decides compatibilidad, precios ni stock, solo el plan.\n"
        f"Herramientas:\n{catalog}\n"
        "Reglas: usa solo part numbers que aparezcan en la situación; termina con finish; "
        "máximo 6 pasos; thought = una frase de máximo 20 palabras; si el cliente busca "
        "sustituto, identifica la pieza y busca sustitutos; "
        "si no hay resultados, intenta relax_requirements; si pregunta algo técnico usa "
        "ask_datasheets; si pide comparar usa compare; si falta información usa ask_customer.\n"
        "Devuelve SOLO un JSON con este esquema: "
        f"{json.dumps(schema, ensure_ascii=False)}\n"
        f"{PLAN_OPEN}\n{situation}\n{PLAN_CLOSE}"
    )
