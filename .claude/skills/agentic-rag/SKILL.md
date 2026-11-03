---
name: agentic-rag
description: Builds the controlled AdvisorAgent state machine, retrievers (BM25, sentence-transformers/FAISS, AI Search) and LLM clients with fallback and output verification. Use when touching src/advisor/{agent,retrieval,llm}/ or prompts.
---

# Agentic RAG

## Alcance
`src/advisor/agent/`, `src/advisor/retrieval/`, `src/advisor/llm/`, `kg.resolve_part`/`candidate_neighbors` como herramientas.

## Máquina de estados
PARSE → RESOLVE → (CLARIFY | STATUS) → DISCOVER → VALIDATE → RANK → COMPOSE → VERIFY. Transiciones explícitas, sin bucles abiertos.
- PARSE: `llm.complete_json` → `ParsedQuery` (Pydantic); si falla la validación ⇒ parser de reglas/plantilla.
- CLARIFY si `PartMatch` ambiguo (scores cercanos) o sin part number ni categoría.
- VALIDATE delega 100 % en `compatibility`.
- VERIFY: cada part number, precio, stock y cifra del texto NLG debe estar en `RecommendationResponse`; si no ⇒ texto de plantilla.

## LLM
Cadena `DatabricksFMAPI` (Llama 3.3 70B) → `Ollama` (qwen3:4b) → `Template`. Timeouts cortos, sin reintentos infinitos. 0 USD.
Prompts reciben solo datos estructurados + chunks; instrucción de no añadir valores.

## Retrieval
`Retriever.search(query, top_k, filters) -> list[ChunkHit]`; BM25 conserva tokens como `E810-CQDA2`, `100GbE`, `RoCEv2`.
Híbrido por RRF. Toda cita = `document_id` + página + `chunk_id` devuelto por el retriever.

## Pruebas
Con `Template` y fixtures: caso E810 produce un ACTIVE con precio/stock del catálogo; consulta ambigua ⇒ CLARIFY; VERIFY rechaza un número inventado.

## Prohibido
Que el agente o el LLM asignen niveles de compatibilidad; llamar APIs de pago; tests que dependan de un LLM real o de red; descargar modelos en tests.
