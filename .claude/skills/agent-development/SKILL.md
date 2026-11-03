---
name: agent-development
description: Use when building or modifying the LangGraph agent, its typed state, tools/function calling, node validations, error handling, or hallucination controls. The agent must call specialized tools (catalog, retrieval, compatibility engine) rather than rely on the LLM's own knowledge.
---

# Desarrollo del agente (LangGraph)

## Principio

El agente es un **orquestador de herramientas deterministas**. El LLM (opcional) interpreta la
petición y redacta la explicación; los hechos vienen de herramientas y la decisión de
compatibilidad viene del motor de `compatibility/`. Con `EMERSON_LLM_PROVIDER=none` el grafo
debe funcionar de extremo a extremo (parsing con reglas, explicación con plantillas).

## Estado tipado

```python
class AgentState(BaseModel):
    request_text: str
    request: ReplacementRequest | None = None  # part_number, must_preserve[], context
    original: Product | None = None
    candidates: list[Product] = []
    evaluations: list[CompatibilityResult] = []  # salida del motor, inmutable
    evidence: list[RetrievedChunk] = []
    answer: ReplacementAnswer | None = None
    errors: list[AgentError] = []
    needs_clarification: str | None = None
```

Usa Pydantic para el estado y para la entrada/salida de cada herramienta. Ninguna herramienta
devuelve `dict` sin validar.

## Grafo

```
parse_request ─► resolve_part ─┬─► (ambiguo/no encontrado) ─► ask_clarification ─► END
                               └─► get_specs ─► find_candidates ─► evaluate_compat
                                   ─► rank ─► explain ─► validate_citations ─┬─► END
                                                                            └─► (fallo) ─► explain (máx. 1 reintento) / degrade
```

- Rutas condicionales con `add_conditional_edges`; nada de bucles sin límite (`recursion_limit`).
- `evaluate_compat` llama al motor; el agente **no puede** modificar un veredicto.
- `validate_citations` comprueba que cada afirmación técnica de la respuesta referencia un
  `chunk_id` presente en `state.evidence` y que ningún candidato `INCOMPATIBLE`/`UNKNOWN` se
  presenta como recomendado. Si falla tras un reintento → respuesta degradada con la tabla
  estructurada y sin texto libre.

## Herramientas

| Herramienta | Entrada | Salida | Fuente |
|---|---|---|---|
| `lookup_product` | part_number (normalizado) | `Product` \| NotFound \| Ambiguous | catálogo gold |
| `get_specifications` | product_id | `list[Specification]` | catálogo gold |
| `search_candidates` | product, must_preserve | `list[Product]` | catálogo (misma categoría) + `product_replacements` |
| `search_documents` | query, filters | `list[RetrievedChunk]` | retrieval |
| `evaluate_compatibility` | original, candidate, request | `CompatibilityResult` | motor determinista |

Contrato de cada herramienta: idempotente, sin efectos laterales, errores tipados
(`ProductNotFound`, `AmbiguousPartNumber`, `RetrievalUnavailable`), tiempo acotado, logs con
`extra={"tool": ..., "part_number": ...}`.

## Control de alucinaciones

- El prompt del LLM recibe **solo** el `CompatibilityResult` serializado y los chunks; instrucción
  explícita: no añadir valores que no aparezcan ahí.
- Salida del LLM con esquema estructurado (`ReplacementAnswer`), no texto libre.
- Post-validación determinista: cada número/unidad mencionado debe existir en las specs o chunks.
- Si el número de parte no existe, el agente lo dice; nunca "adivina" una pieza parecida.
- Datos sintéticos: la respuesta incluye el aviso "datos de demostración sintéticos".

## Manejo de errores

- Cada nodo captura excepciones de dominio y las añade a `state.errors`; las inesperadas se
  propagan (fallar ruidosamente es preferible a una recomendación silenciosa errónea).
- Recuperación caída → continuar con catálogo estructurado, marcando "sin evidencia documental"
  → los veredictos que dependían de evidencia bajan a `UNKNOWN`.

## Ejemplo de uso esperado

> "Necesito reemplazar SYN-PT-100 porque está descontinuado; conservar características eléctricas y la conexión."

`must_preserve = [supply_voltage, output_signal, protocol, process_connection]` → se elevan a
HARD → resultado: 1 CONFIRMED, 1 CONDITIONAL (adaptador), 1 UNKNOWN, 1 INCOMPATIBLE, con fuentes.

## Errores a evitar

- Dejar que el LLM "compare" especificaciones o asigne veredictos.
- Herramientas que devuelven texto libre en vez de modelos tipados.
- Reintentos infinitos o grafos sin `recursion_limit`.
- Prompts que piden "sé útil y sugiere algo aunque no haya datos".
- Llamar a APIs de pago sin autorización; el LLM está apagado por defecto.
- Tests que dependen de un LLM real (usa `LLMProvider.NONE` o un fake determinista).
