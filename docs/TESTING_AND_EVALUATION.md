# Testing and Evaluation

## Niveles
| Carpeta | Contenido | Política |
|---|---|---|
| `tests/contracts/` | modelos e imports | siempre verde |
| `tests/unit/` | lógica por módulo; stubs marcados `xfail(raises=NotImplementedError)` | quien implementa el contrato quita el xfail |
| `tests/integration/` | flujo sobre fixtures | — |
| `tests/data/` | sobre PDFs reales (32 filas de catálogo, 32 datasheets) | — |

## Evaluación (`evaluation/gold_set.yaml`)
Métricas: exactitud de resolución de part number, exactitud de estado, hit@k del sustituto esperado, exactitud de nivel de compatibilidad,
tasa de recomendaciones no-ACTIVE (objetivo 0), tasa de cifras no verificadas en NLG (objetivo 0).

## Casos negativos obligatorios
Recomendar un producto no ACTIVE; precio en producto no ACTIVE; categoría distinta como COMPATIBLE; dato faltante como COMPATIBLE.

## Evaluación implementada (B-22)

`make eval` (= `python -m evaluation.run_eval`) ejecuta el `AdvisorAgent` real con LLM `template` sobre
`evaluation/gold_set.yaml` y escribe `evaluation/report.md` (versionado) y `artifacts/eval/results.json`.

| Métrica | Definición |
|---|---|
| resolution_accuracy | part number resuelto = `expected_original` (casos sin aclaración) |
| status_accuracy | estado del original = catálogo |
| clarification_accuracy | pide aclaración solo cuando se espera, y sugiere `clarification_mentions` |
| hit_at_1 | 1.ª recomendación confirmada ∈ `expected_top`; con `expected_top: []`, ninguna confirmada |
| mrr_recommendation | 1/rango del primer sustituto aceptable |
| level_accuracy | nivel de la 1.ª recomendación = `expected_level` |
| retrieval P@3, P@5, R@5, MRR | BM25 → ranking de documentos vs `relevant_documents` |
| gate_* (deben ser 0) | prohibidas recomendadas, no-ACTIVE recomendadas, precio/stock ≠ catálogo, texto con cifras no verificadas |

`tests/data/test_evaluation.py` comprueba la integridad del golden set **contra el catálogo** (part numbers existen,
estados coinciden, `expected_top` solo ACTIVE) y que las puertas pasen.
