# Compatibility Engine Design

## Niveles (`CompatibilityLevel`)
| Nivel | Condición |
|---|---|
| COMPATIBLE | todas las reglas críticas pasan con evidencia |
| COMPATIBLE_WITH_CONDITIONS | críticas pasan; alguna no crítica falla o requiere acción (adaptador, firmware, upgrade) |
| UNKNOWN | falta dato para alguna regla crítica (R-MISSING) |
| INCOMPATIBLE | alguna regla crítica falla |

Precedencia: INCOMPATIBLE > UNKNOWN > COMPATIBLE_WITH_CONDITIONS > COMPATIBLE.

## Reglas (`config/compat_rules.yaml`)
R-CAT (categoría), R-FF (form factor/encapsulado), R-MUST-PROTO (protocolos obligatorios), R-ELEC (eléctricas),
R-NUM-GTE (numéricas mayor-o-igual), R-UPGRADE (mejora aceptable), R-MISSING (dato ausente).

## Flujo
1. `derive_requirements(original, parsed_query)` → `list[TechnicalRequirement]` (origen: QUERY, ORIGINAL_SPEC, CATEGORY_DEFAULT).
2. `evaluate(original, candidate, requirements)` → `CompatibilityResult` con `RuleResult` por regla.
3. Matriz 32×32 precalculada (`databricks/notebooks/05_compat_matrix.py`) para la demo.

## Prohibiciones
Sin LLM, sin retrieval, sin red. Similitud semántica nunca concede compatibilidad. Desconocido ≠ compatible.
