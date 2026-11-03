# Evaluación — Emerson Replacement Advisor

Generado por `make eval` el 2026-11-03 · LLM: `template` · retriever: `bm25` · 32 casos de `evaluation/gold_set.yaml` (verificados contra los PDFs).

**Puertas de seguridad:** OK (todas en 0)

| Métrica | Valor |
|---|---|
| cases | 32 |
| resolution_accuracy | 1.00 |
| status_accuracy | 1.00 |
| clarification_accuracy | 1.00 |
| hit_at_1 | 1.00 |
| mrr_recommendation | 1.00 |
| level_accuracy | 1.00 |
| retrieval_precision_at_3 | 0.35 |
| retrieval_precision_at_5 | 0.22 |
| retrieval_recall_at_5 | 0.88 |
| retrieval_mrr | 0.83 |
| retrieval_mrr_semantic_cases | 0.56 |
| retrieval_recall_at_5_semantic_cases | 0.70 |
| gate_forbidden_recommendations | 0 |
| gate_non_active_recommendations | 0 |
| gate_price_stock_mismatches | 0 |
| gate_unverified_text | 0 |

## Por caso

| Caso | Resuelto | Res. | Estado | Aclar. | Hit@1 | Nivel | Recomendaciones | P@3 | R@5 | MRR ret. |
|---|---|---|---|---|---|---|---|---|---|---|
| GS-01 | E810-CQDA2 | ✓ | ✓ | ✓ | ✓ | ✓ | MCX75310AAS-NEAT, BCM57508 | 1.00 | 1.00 | 1.00 |
| GS-02 | E810-CQDA2 | ✓ | ✓ | ✓ | ✓ | ✓ | MCX75310AAS-NEAT, BCM57508 | 0.33 | 1.00 | 1.00 |
| GS-03 | — | — | — | ✓ | — | — | — | — | — | — |
| GS-04 | E810-CQDA2 | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — |
| GS-05 | USB-2627 | ✓ | ✓ | ✓ | ✓ | ✓ | USB-2633 | 0.67 | 1.00 | 1.00 |
| GS-06 | USB-2627 | ✓ | ✓ | ✓ | ✓ | — | USB-2633 | — | — | — |
| GS-07 | USB-1608GX | ✓ | ✓ | ✓ | ✓ | ✓ | USB-2633, USB-1808X | 0.33 | 1.00 | 1.00 |
| GS-08 | USB-6001 | ✓ | ✓ | ✓ | ✓ | — | USB-2633, USB-1808X | 0.33 | 1.00 | 1.00 |
| GS-09 | — | ✓ | — | ✓ | ✓ | ✓ | USB-2633 | 0.33 | 1.00 | 1.00 |
| GS-10 | A100-SXM4-80GB | ✓ | ✓ | ✓ | ✓ | — | — | 0.33 | 1.00 | 1.00 |
| GS-11 | — | ✓ | — | ✓ | ✓ | ✓ | MI300X, H100-SXM5 | 1.00 | 1.00 | 1.00 |
| GS-12 | ATSAMD21G18A | ✓ | ✓ | ✓ | ✓ | ✓ | ESP32-S3, RP2040, STM32H743ZIT6 | 0.33 | 1.00 | 1.00 |
| GS-13 | MPU-6050 | ✓ | ✓ | ✓ | ✓ | — | — | 0.33 | 1.00 | 1.00 |
| GS-14 | WUS4C6464DSP3X5 | ✓ | ✓ | ✓ | ✓ | — | — | 0.33 | 1.00 | 1.00 |
| GS-15 | IR3555MTRPBF | ✓ | ✓ | ✓ | ✓ | — | — | 0.33 | 1.00 | 1.00 |
| GS-16 | XC7A200T | ✓ | ✓ | ✓ | ✓ | ✓ | AGFB014R24A | 0.33 | 1.00 | 1.00 |
| GS-17 | Cortex-A78 | ✓ | ✓ | ✓ | ✓ | — | — | 0.33 | 1.00 | 1.00 |
| GS-18 | MCX75310AAS-NEAT | ✓ | ✓ | ✓ | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-19 | BCM57508 | ✓ | ✓ | ✓ | — | — | MCX75310AAS-NEAT | — | — | — |
| GS-20 | — | — | — | ✓ | — | — | — | — | — | — |
| GS-21 | — | — | — | ✓ | — | — | — | — | — | — |
| GS-22 | — | — | — | ✓ | — | — | — | — | — | — |
| GS-R01 | — | — | — | — | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-R02 | — | — | — | — | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-R03 | — | — | — | — | — | — | — | 0.00 | 0.00 | 0.00 |
| GS-R04 | — | — | — | — | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-R05 | — | — | — | — | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-R06 | — | — | — | — | — | — | — | 0.33 | 1.00 | 0.33 |
| GS-R07 | — | — | — | — | — | — | — | 0.00 | 0.00 | 0.00 |
| GS-R08 | — | — | — | — | — | — | — | 0.33 | 1.00 | 1.00 |
| GS-R09 | — | — | — | — | — | — | — | 0.00 | 1.00 | 0.25 |
| GS-R10 | — | — | — | — | — | — | — | 0.00 | 0.00 | 0.06 |

## Cómo leer estas cifras

- El golden set es pequeño (~20 casos) y lo escribió el mismo equipo a partir de
  los PDFs. Dos fallos de su primera ejecución (alias de modelo 'SN860' y sugerencia
  ante erratas) se corrigieron en el sistema: un 1.00 indica consistencia con casos
  conocidos, no generalización. Faltan un conjunto ciego y un experto de dominio.
- Precision@K de recuperación está acotada por construcción: con 1 documento
  relevante, P@3 <= 0.33. Recall@5 y MRR son más informativas (33 PDFs).
- Las puertas `gate_*` son bloqueantes: `make eval` falla si alguna es > 0.
- LLM `template` = sin modelo (determinista); `--llm configured` usa la cadena de settings.
