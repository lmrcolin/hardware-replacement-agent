# Cost Model

`make excel` (`scripts/build_tco_excel.py`) genera `cost/emerson_advisor_tco.xlsx` (versionado como entregable).

## Hojas

| Hoja | Contenido |
|---|---|
| Supuestos | cada entrada como celda con nombre; **DATO** (con fuente) o **SUPUESTO** (amarillo, editable) |
| Desarrollo | prototipo del datathon (personas × horas efectivas × tarifa) + endurecimiento a piloto + APIs del reto |
| Mantenimiento_1_anio | horas de mantenimiento y actualización de catálogo; DBU del pipeline y del warehouse; tokens LLM; hospedaje |
| TCO_anual | desarrollo + operación + contingencia; TCO año 1 y años siguientes; comparación con la meta de 4 M USD/año |
| Inventario | datos reales del catálogo: precio solo en ACTIVE, stock, valor (fórmula) y totales |

Todas las hojas salvo Supuestos e Inventario contienen solo fórmulas: al editar un supuesto se recalcula el libro
(verificado con LibreOffice en `tests/integration/test_tco_excel.py`).

## Entradas

| Nombre | Parámetro | Valor por defecto | Unidad | Tipo | Fuente / nota |
|---|---|---|---|---|---|
| `personas_equipo` | Personas en el equipo | 3 | personas | DATO | Equipo del datathon (3 personas) |
| `horas_reto` | Duración del reto | 24 | h | DATO | Reto de 24 h (Datathon MICAI 2026) |
| `objetivo_inventario_usd` | Inventario a mover por año (meta) | 4e+06 | USD/año | DATO | Meta del Reto 1 de Emerson |
| `costo_apis_hackathon_usd` | Costo de APIs durante el reto | 0 | USD | DATO | Regla del reto: APIs = 0 USD (Free Edition + plantilla/Ollama) |
| `horas_efectivas_persona` | Horas productivas por persona en el reto | 20 | h/persona | SUPUESTO | SUPUESTO EDITABLE: horas útiles de las 24 del reto |
| `tarifa_usd_hora` | Tarifa de desarrollo | 30 | USD/h | SUPUESTO | SUPUESTO EDITABLE: reemplazar por la tarifa interna de Emerson |
| `horas_endurecimiento` | Horas para pasar de prototipo a piloto | 120 | h | SUPUESTO | SUPUESTO EDITABLE: seguridad, CI/CD, monitoreo, UI final |
| `horas_mantenimiento_mes` | Mantenimiento (reglas, monitoreo, soporte) | 12 | h/mes | SUPUESTO | SUPUESTO EDITABLE |
| `actualizaciones_catalogo_anio` | Actualizaciones de catálogo por año | 12 | veces/año | SUPUESTO | SUPUESTO EDITABLE: una por mes |
| `horas_por_actualizacion` | Horas por actualización de catálogo | 2 | h | SUPUESTO | SUPUESTO EDITABLE: subir PDFs + run_all + revisar JoinReport |
| `dbu_por_ejecucion` | DBU por ejecución del job run_all | 2 | DBU | SUPUESTO | POR CONFIRMAR: medir en system.billing.usage tras un run |
| `ejecuciones_mes` | Ejecuciones del pipeline por mes | 4 | veces/mes | SUPUESTO | SUPUESTO EDITABLE |
| `warehouse_horas_mes` | Horas de SQL warehouse por mes | 40 | h/mes | SUPUESTO | SUPUESTO EDITABLE |
| `dbu_hora_warehouse` | DBU por hora del warehouse 2X-Small | 4 | DBU/h | SUPUESTO | POR CONFIRMAR en la documentación de precios de Databricks |
| `usd_por_dbu` | Precio por DBU (plan de pago) | 0.7 | USD/DBU | SUPUESTO | POR CONFIRMAR: depende de plan, nube y tipo de cómputo; Free Edition = 0 |
| `consultas_mes` | Consultas de clientes por mes | 1000 | consultas/mes | SUPUESTO | SUPUESTO EDITABLE |
| `tokens_por_consulta` | Tokens LLM por consulta (NLU + NLG) | 3000 | tokens | SUPUESTO | SUPUESTO EDITABLE: medir con trazas reales |
| `usd_por_millon_tokens` | Precio LLM por millón de tokens | 1 | USD/1M tokens | SUPUESTO | POR CONFIRMAR: precio pay-per-token de Llama 3.3 70B en FMAPI; plantilla = 0 |
| `hosting_app_usd_mes` | Hospedaje de la app | 50 | USD/mes | SUPUESTO | SUPUESTO EDITABLE: Databricks App o VM pequeña |
| `contingencia_pct` | Contingencia | 0.15 | % | SUPUESTO | SUPUESTO EDITABLE |

**Importante:** los valores SUPUESTO son de partida para que el modelo calcule; los marcados **POR CONFIRMAR**
(precio por DBU, DBU por hora del warehouse, DBU por ejecución, precio por millón de tokens) deben sustituirse por
precios oficiales o por mediciones reales (`system.billing.usage`) antes de presentar cifras como definitivas.

## Resultado con los valores por defecto (recalculado)

| Concepto | USD |
|---|---|
| Desarrollo | 5,400.00 |
| Mantenimiento y operación (12 meses) | 7,087.20 |
| Contingencia (15 %) | 1,873.08 |
| **TCO año 1** | **14,360.28** |
| TCO años siguientes | 8,150.28 |
| TCO año 1 / meta de 4 M USD de inventario | 0.36 % |

Datos reales del catálogo: valor del inventario ACTIVE = 12,814,325.00 USD; 11 piezas no ACTIVE con 512 unidades en
stock sin precio vigente (XC7A200T 500, A100 12). Durante el reto, APIs = 0 USD (Free Edition + plantilla).
