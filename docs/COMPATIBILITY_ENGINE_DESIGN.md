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

## Implementación (B-14..B-17)

- **Requisitos** (`derive_requirements`): los de la consulta primero; después las specs del original según
  `spec_registry.yaml` (`critical` → MUST, resto → SHOULD; `compare` decide el operador; `derive: false` = informativo).
- **Severidad por requisito:** MUST → CRITICAL, SHOULD → MAJOR, NICE → MINOR.
- **Comparaciones:** `gte`/`lte` con conversión de unidades; `interface` (PCIe/USB retrocompatibles → condición,
  más carriles que la ranura o familia distinta → FAIL); `has_all` por ítem; `intersects` (form factor, bus);
  `eq` normalizado. `upgrade_condition` convierte una mejora que cambia la integración en condición (R-UPGRADE).
- **Puntuación:** `coverage` = MUST satisfechos; `score` = media ponderada (CRITICAL 3, MAJOR 2, MINOR 1;
  PASS 1, CONDITIONAL 0.7, MISSING 0.3, FAIL 0). Ranking: nivel > coverage > score > stock > part number.

## Resultados sobre el catálogo real (solo requisitos derivados del original)

| Original | Estado | Recomendación | Motivo principal |
|---|---|---|---|
| E810-CQDA2 (+ consulta oficial) | DISCONTINUED | 1. MCX75310AAS-NEAT, 2. BCM57508 (con condiciones) | 400/200 GbE, PCIe 5.0 retrocompatible, NVGRE/iWARP no declarados |
| USB-2627 | DISCONTINUED | USB-2633 (con condiciones) | USB 3.0 retrocompatible; el resto no llega a 64 entradas |
| USB-1608GX / USB-6001 | DISCONTINUED / EOL | USB-2633, USB-1808X | AD7606 es SPI/paralelo, no USB |
| ATSAMD21G18A | DISCONTINUED | ESP32-S3, RP2040, STM32H743 (con condiciones) | otro núcleo ⇒ portar firmware |
| XC7A200T | NRND | AGFB014R24A (con condiciones) | iCE40 no llega a 215K celdas |
| A100-SXM4-80GB | NRND | ninguna | H100-SXM5: factor de forma SXM5 ≠ SXM4 (el datasheet lo llama sucesor, pero no es drop-in) |
| MPU-6050 | DISCONTINUED | ninguna | BME680 no mide giroscopio/acelerómetro |
| WUS4C6464DSP3X5 | DISCONTINUED | ninguna | 990 PRO: 2 TB < 6.4 TB, M.2 ≠ U.2 |
| IR3555MTRPBF | EOL | ninguna | TPS65982 es controlador USB-PD (otra función) |
| Cortex-A78 | NRND | w9-3595X solo como UNKNOWN | EPYC: Zen 4 ≠ ARMv8.2A; el Xeon no declara arquitectura |

**Decisión abierta (equipo):** los candidatos UNKNOWN hoy aparecen al final de `recommendations` con su nivel explícito.
Alternativa: moverlos a una lista propia (`unverified_options`), lo que requiere un PR `contract-change`.
