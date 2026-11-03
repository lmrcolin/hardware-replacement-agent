# Project Overview — Emerson Replacement Advisor

**Reto:** Datathon MICAI 2026, Reto 1 (Emerson). Ante una pieza DISCONTINUED/EOL/NRND, recomendar sustitutos
**ACTIVE** del catálogo considerando especificaciones, compatibilidad, precio y stock, con justificación trazable.
**Meta de negocio:** mover ~4 M USD/año de inventario hacia productos activos.

## Fuentes
- `data/raw/Catalogo_Comercial_Precios_Inventario_2026.pdf` — 32 part numbers (estado, fechas, precio si ACTIVE, stock).
- 32 datasheets (por producto o familia). Ver [DATA_INVENTORY.md](DATA_INVENTORY.md).

## Caso oficial
> "Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. Usábamos la Intel E810 pero ya no la encuentro."

Salida esperada: detectar E810-CQDA2 DISCONTINUED → recomendar sustituto ACTIVE con part number, precio, unidades,
nivel de compatibilidad, requisitos cubiertos/no cubiertos y evidencia.

## Entregables
Código y notebooks · instrucciones de reproducción · demo en vivo · Excel (desarrollo, mantenimiento 1 año, TCO anual).

## Rúbrica
| Criterio | Peso | Dónde se demuestra |
|---|---|---|
| Entendimiento | 10 | PROJECT_OVERVIEW, REQUIREMENTS_ANALYSIS |
| Enriquecimiento | 15 | extraction + enrichment + KG |
| Búsqueda/matching | 20 | retrieval + kg + compatibility |
| Recomendación | 25 | compatibility + commercial + recommendation + agent |
| Experiencia | 15 | Streamlit + DEMO_PLAN |
| Reproducibilidad | 15 | `scripts/reproduce_from_scratch.sh`, bundle `run_all`, `make check` |
