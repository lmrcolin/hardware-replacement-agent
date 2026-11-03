---
name: evaluation-testing
description: Use when writing pytest unit/integration tests, building golden datasets, computing retrieval metrics (Precision@K, Recall@K, MRR), measuring compatibility verdict accuracy, evaluating agent answers, or adding negative/safety tests that block technically dangerous recommendations.
---

# Evaluación y testing

## Pirámide de tests

| Nivel | Qué | Dónde | Velocidad |
|---|---|---|---|
| Unit | modelos Pydantic, conversión de unidades, comparadores, agregación de veredictos, métricas | `tests/unit/` | ms, sin red ni Spark |
| Safety | casos negativos que nunca deben recomendarse | `tests/unit/` con `@pytest.mark.safety` | ms |
| Integration | catálogo sintético → motor → agente (LLM=none) → respuesta | `tests/integration/` `@pytest.mark.integration` | s |
| Spark | transforms con SparkSession local | `@pytest.mark.spark`, se omite si falta pyspark | s |
| Eval offline | golden set → métricas → MLflow (opcional) | `scripts/` / notebook `06_evaluation` | min |

`make test` ejecuta todo menos lo que requiera extras no instalados (`pytest.importorskip("pyspark")`).

## Métricas de recuperación

Para cada consulta `q` con conjunto relevante `R_q` y ranking `L_q`:

- `Precision@K = |top_K(L_q) ∩ R_q| / K`
- `Recall@K = |top_K(L_q) ∩ R_q| / |R_q|`
- `MRR = media(1 / rank del primer relevante)` (0 si no aparece)

Implementa las métricas como funciones puras y **testéalas con casos calculados a mano**,
incluidos `R_q` vacío (definir comportamiento explícito) y K mayor que la lista.

## Métricas de compatibilidad

- **Exactitud de veredicto** y matriz de confusión 4×4 (CONFIRMED/CONDITIONAL/UNKNOWN/INCOMPATIBLE).
- **Tasa de recomendación peligrosa** = casos con verdad `INCOMPATIBLE` o `UNKNOWN` predichos como
  `CONFIRMED`. **Objetivo: 0. Es un test que bloquea el merge, no una métrica a optimizar.**
- Precisión de atributos que justifican el veredicto (¿se identificó el atributo HARD correcto?).

## Evaluación de respuestas

- Fidelidad: cada valor numérico de la respuesta existe en specs/chunks (comprobación determinista).
- Cobertura de citas: % de afirmaciones con `chunk_id` válido (objetivo 100 %).
- Completitud: la respuesta incluye coincidencias, diferencias, restricciones, desconocidos y fuentes.
- Aviso de datos sintéticos presente cuando corresponde.

## Casos negativos obligatorios (safety)

1. Señal distinta (4–20 mA vs 0–10 V) → `INCOMPATIBLE`.
2. Tensión AC vs DC con el mismo número → `INCOMPATIBLE`.
3. Rango de presión del candidato menor que el de operación → `INCOMPATIBLE`.
4. Presión absoluta vs manométrica sin conversión → nunca `CONFIRMED`.
5. Certificación ATEX requerida ausente en el candidato → `UNKNOWN` o `INCOMPATIBLE`, nunca `CONFIRMED`.
6. Atributo HARD sin dato → `UNKNOWN`.
7. Descripción casi idéntica pero protocolo distinto (HART vs FOUNDATION Fieldbus) → `INCOMPATIBLE`.
8. Unidad desconocida o incompatible dimensionalmente → no `MATCH`.
9. Número de parte inexistente → el agente no inventa ningún producto.
10. Un score de ranking alto no puede promover un `INCOMPATIBLE`.

## Ejemplo

```python
@pytest.mark.safety
@pytest.mark.parametrize("candidate_signal", ["0-10V", "1-5V", None])
def test_signal_mismatch_or_missing_is_never_confirmed(make_transmitter, candidate_signal):
    original = make_transmitter(output_signal="4-20mA")
    candidate = make_transmitter(output_signal=candidate_signal)
    result = evaluate(original, candidate, must_preserve={"output_signal"})
    assert result.verdict is not Verdict.CONFIRMED
```

## Criterios de calidad

- Tests deterministas: semillas fijas, sin red, sin LLM real (`LLMProvider.NONE` o fakes).
- Fixtures sintéticos pequeños en `tests/fixtures/` o construidos con factories.
- Un test = un comportamiento; nombres que describen la regla (`test_hard_missing_yields_unknown`).
- Cobertura objetivo ≥ 90 % en `compatibility/` y `evaluation/`.
- Cada bug encontrado añade un test de regresión antes del fix.

## Errores a evitar

- Testear solo el camino feliz (todo `CONFIRMED`).
- Snapshots de texto del LLM como oráculo.
- Métricas sin casos frontera (listas vacías, K=0, duplicados en el ranking).
- Aceptar una "tasa de recomendación peligrosa" > 0 a cambio de más recall.
- Tests que pasan con Spark local y se asumen válidos en Databricks.
