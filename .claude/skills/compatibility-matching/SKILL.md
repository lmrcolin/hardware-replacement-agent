---
name: compatibility-matching
description: Implements and reviews the deterministic compatibility engine, YAML rules, requirement derivation, 32x32 matrix and lexicographic ranking. Use when touching src/advisor/compatibility/, src/advisor/recommendation/, src/advisor/commercial/ or config/compat_rules.yaml.
---

# Compatibility matching and ranking

## Alcance
`src/advisor/{compatibility,recommendation,commercial}/`, `config/compat_rules.yaml`, notebook `06_compat_matrix`.

## Regla de oro
Compatibilidad = reglas deterministas sobre specs con evidencia. **Nunca** por similitud semántica ni por opinión del LLM.

## Niveles y precedencia
INCOMPATIBLE > UNKNOWN > COMPATIBLE_WITH_CONDITIONS > COMPATIBLE.
- Regla crítica falla ⇒ INCOMPATIBLE.
- Dato crítico faltante (R-MISSING) ⇒ UNKNOWN.
- No crítica falla o requiere acción (adaptador, firmware) ⇒ COMPATIBLE_WITH_CONDITIONS.

## Reglas (compat_rules.yaml)
R-CAT, R-FF, R-MUST-PROTO, R-ELEC, R-NUM-GTE, R-UPGRADE, R-MISSING. Operadores de `TechnicalRequirement`: EQ, GTE, LTE, IN, HAS.
Comparar siempre en unidades canónicas de `spec_registry.yaml`; unidades incompatibles ⇒ MISSING, no MATCH.

## Ranking (`recommendation.rank`)
Clave lexicográfica: (nivel, cobertura de requisitos MUST, score) — **inventario/stock solo desempata**. Solo `status == ACTIVE` entra en
`recommendations`; NRND en `risky_options`; DISCONTINUED/EOL excluidos. Precio y stock vienen de `CommercialEngine` (catálogo).

## Pruebas obligatorias (tests/unit)
- Categoría distinta ⇒ INCOMPATIBLE.
- Protocolo obligatorio ausente (p. ej. RDMA) ⇒ INCOMPATIBLE.
- Dato crítico ausente ⇒ UNKNOWN, nunca COMPATIBLE.
- Mayor stock no supera a mejor nivel.
- Ningún no-ACTIVE en `recommendations`.
- Matriz 32×32: diagonal excluida, simetría NO asumida.

## Prohibido
Importar `advisor.llm`, `advisor.retrieval`, `httpx`, `databricks` (import-linter lo bloquea); scores que promuevan un nivel; equivalencias técnicas inventadas.
