# Agent Design

Agente con herramientas (ADR-014, contrato 1.2.0): **el LLM planifica qué herramientas usar; las herramientas son
deterministas y deciden**. Compatibilidad, estado, precio y stock nunca salen del LLM.

```
NLU (ParsedQuery validado) → MEMORIA (ConversationContext) → PLAN (Llama: AgentPlan JSON | reglas)
   → ejecutar herramientas con GUARDIÁN → COMPOSE (borrador determinista) → NLG (Llama) → VERIFY
```

| Herramienta | Qué hace (determinista) | Pasos internos (`last_trace`) |
|---|---|---|
| `lookup_part` | `kg.resolve_part` + prefijos únicos ("la MCX"); ambigüedad o errata ⇒ pregunta con opciones | RESOLVE, STATUS |
| `find_substitutes` | candidatos (categoría + grafo + búsqueda) → `derive_requirements` + `evaluate` + `rank` | DISCOVER, VALIDATE, RANK |
| `search_catalog` | sin part number: evalúa la categoría contra los requisitos de la consulta | DISCOVER, VALIDATE, RANK |
| `relax_requirements` | sin resultados: quita **un** requisito que bloqueó candidatos (FAIL) y dice qué se podría vender; nunca los `negotiable: false` (ISA, función, magnitudes) | RELAX |
| `ask_datasheets` | specs extraídas que la pregunta nombra (con evidencia) + fragmentos citados (sin frases de precio/stock: el catálogo manda) | ANSWER |
| `compare` | specs lado a lado, datos comerciales y si B sustituye a A según las reglas | COMPARE |
| `ask_customer` | la pregunta que más separa los productos ACTIVE de la categoría (críticas primero), con opciones | CLARIFY |

**Planificador** (`agent/planner.py`): con un LLM disponible, Llama devuelve `AgentPlan` (pensamiento + pasos,
JSON validado). Cada paso pasa por `check()`: si no aplica (p. ej. `ask_customer` cuando ya hay resultados, `finish`
antes de buscar) se sustituye por la política de reglas `rule_action()` y queda registrado como
`rules (corrige a <llm>: motivo)`. Sin LLM (`template`), `rule_action()` decide todo: el flujo funciona igual.
Máximo 6 pasos. Cada `ToolCall` (herramienta, argumentos, resumen, quién la eligió, pensamiento) va en la respuesta.

**Memoria** (`ConversationContext` en `CustomerQuery.context` / `RecommendationResponse.context`): pieza original,
categoría, requisitos acumulados, recomendados del último turno y clave de la última pregunta. El agente es sin
estado; la UI reenvía el contexto. Seguimientos: "¿y la más barata?" (reordena por precio dentro del mismo nivel),
"compárala con la BCM57508" (referencia = recomendado anterior), "ya no necesito IPsec" (`ParsedQuery.remove`),
"con 200 me basta" (una cifra nueva reemplaza la recordada), "400 Gb/s" tras una pregunta (categoría recordada).
Mencionar otra pieza u otra categoría empieza un tema nuevo.

**NLU**: el LLM produce `ParsedQuery`; se sanea (claves del registro, cifras presentes en el texto, EQ→GTE/LTE,
sinónimos). Las intenciones explícitas por palabras (reemplazo, comparación, pregunta) prevalecen sobre el LLM.

**VERIFY**: toda cifra o part number del texto del LLM debe estar en el borrador o el catálogo; si no, se muestra
el borrador y se avisa. Cadena LLM: `databricks` con perfil explícito, o con el perfil por defecto cuando el modo es
Databricks (Delta o AI Search); `ollama` si responde; `template` siempre al final.
