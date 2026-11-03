---
name: streamlit-product
description: Builds the Streamlit customer-facing UI, reusable components and the MockAdvisorAgent, reading only from artifacts via repository. Use when touching app/ or tests that render the UI.
---

# Streamlit product

## Alcance
`app/streamlit_app.py`, `app/components/`, `app/mock_agent.py`.

## Convenciones
- La app solo importa `advisor.models`, `advisor.agent`, `advisor.repository`, `advisor.config` y `advisor.pipeline` (para `build_agent`).
- Toda vista consume `RecommendationResponse`; sin lógica de negocio en la UI.
- `MockAdvisorAgent` (fixtures) hasta que exista `AdvisorAgent`; selector en la barra lateral.
- Mostrar por recomendación: part number, fabricante, nivel (badge), precio y stock del catálogo, requisitos cubiertos/no cubiertos, condiciones, evidencia (documento/página).
- NRND en sección "Opciones con riesgo"; datos sintéticos con aviso visible.
- Profesional y sobria: sin emojis decorativos; tablas legibles; copy en español.

## Pruebas
`streamlit run app/streamlit_app.py` arranca con el mock; los 3 `RecommendationResponse` de fixtures se renderizan sin error.

## Prohibido
Calcular compatibilidad o ranking en la UI; mostrar precio de productos no ACTIVE; llamar a Databricks o LLMs directamente desde la UI.
