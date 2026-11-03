# 24-Hour Roadmap

Frentes de trabajo, no personas: cualquiera toma cualquier tarea y lo anuncia en el chat del equipo.

| Hora | Datos | Inteligencia | Producto |
|---|---|---|---|
| 0–2 | auth + `bundle run run_all` (00_setup, 01_parse) | tests de compatibilidad sobre fixtures | app con MockAdvisorAgent |
| 2–6 | parse_catalog + extract_product | compat rules + evaluate | repository LocalParquet + vistas |
| 6–10 | join_catalog + chunking + build_graph | resolve_part + candidate_neighbors + rank | gold_set real + eval |
| 10–14 | notebooks 02–06, artefactos | agent end-to-end + LLM fallback | integración app ↔ agente |
| 14–18 | reproducibilidad desde cero | VERIFY + casos difíciles | Excel TCO + DEMO_PLAN |
| 18–22 | congelación de datos | ajustes de ranking | ensayo de demo |
| 22–24 | buffer | buffer | entrega |
TODO: ajustar con horarios reales del evento.
