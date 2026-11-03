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
