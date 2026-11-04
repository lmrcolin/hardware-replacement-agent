# Emerson Replacement Advisor

Asistente agéntico desarrollado para el Datathon MICAI 2026, Reto 1 (Emerson). Ante una pieza de hardware
descontinuada (DISCONTINUED), en fin de vida (EOL) o no recomendada para diseños nuevos (NRND), el sistema
identifica la pieza en el catálogo, recomienda sustitutos activos (ACTIVE) técnicamente compatibles e informa su
precio, sus unidades disponibles, las condiciones de instalación y la evidencia de los datasheets que respalda cada
afirmación.

El presente documento describe, paso a paso, cómo instalar, ejecutar y verificar la solución, tanto en un equipo
local (sin cuentas ni conexión a servicios externos) como en Databricks Free Edition.

## Contenido

1. [Descripción general](#1-descripción-general)
2. [Requisitos previos](#2-requisitos-previos)
3. [Ejecución local](#3-ejecución-local)
4. [Verificación de la instalación](#4-verificación-de-la-instalación)
5. [Ejecución completa en Databricks Free Edition](#5-ejecución-completa-en-databricks-free-edition)
6. [Configuración opcional](#6-configuración-opcional)
7. [Referencia de comandos](#7-referencia-de-comandos)
8. [Solución de problemas](#8-solución-de-problemas)
9. [Arquitectura](#9-arquitectura)
10. [Resultados de la evaluación](#10-resultados-de-la-evaluación)
11. [Limitaciones conocidas](#11-limitaciones-conocidas)
12. [Estructura del repositorio y documentación adicional](#12-estructura-del-repositorio-y-documentación-adicional)

---

## 1. Descripción general

### 1.1 Problema que resuelve

Cuando un cliente solicita una pieza que ya no se comercializa, la venta se pierde a menos que alguien identifique
a tiempo un sustituto activo, compatible y en existencia; hoy esa tarea depende de expertos. El catálogo entregado
contiene 32 piezas: 11 no vendibles (6 DISCONTINUED, 2 EOL y 3 NRND) y 21 ACTIVE, cuyo inventario asciende a
12,814,325.00 USD a precio de catálogo (precio multiplicado por existencias). La meta comercial es mover
aproximadamente 4 millones de USD al año. El asistente transforma cada consulta sobre una pieza obsoleta en una
oferta vendible en segundos y, cuando no existe un sustituto, lo declara y explica qué candidatos se descartaron y
por qué.

### 1.2 Resultado esperado del caso oficial

Consulta: *"Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. Usábamos la Intel
E810 pero ya no la encuentro."*

Respuesta del sistema:

- La pieza E810-CQDA2 figura como DISCONTINUED desde el 1 de agosto de 2025.
- Opción 1: MCX75310AAS-NEAT (NVIDIA ConnectX-7 400GbE), 1,250.00 USD, 120 unidades, compatible con condiciones.
- Opción 2: BCM57508 (Broadcom 200GbE), 890.00 USD, 75 unidades, compatible con condiciones.
- Cada opción muestra la comparación de especificaciones, las condiciones (por ejemplo, validar ópticas o usar
  breakout por la mayor velocidad de puerto) y las citas del datasheet correspondiente con número de página.

### 1.3 Principios de funcionamiento

- El catálogo comercial es la única fuente de verdad para estado, precio y existencias.
- La compatibilidad la decide un motor de reglas determinista. Si una regla crítica falla, el candidato es
  incompatible; si falta un dato crítico, el candidato no se recomienda y se presenta aparte para validación de un
  experto.
- Solo se recomiendan piezas ACTIVE. Las piezas NRND se muestran como opciones con riesgo. Las DISCONTINUED y EOL
  nunca se recomiendan.
- El modelo de lenguaje interpreta la consulta, propone qué herramientas utilizar y redacta la respuesta, pero no
  decide la compatibilidad ni introduce cifras: toda cifra del texto final se verifica contra los datos
  estructurados antes de mostrarse.

---

## 2. Requisitos previos

### 2.1 Para la ejecución local

| Componente | Versión | Finalidad | Instalación |
|---|---|---|---|
| uv | 0.4 o superior | Instala Python 3.12 y todas las dependencias en un entorno aislado | Linux y macOS: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`. Alternativa: `pipx install uv` |
| Git | Cualquiera reciente | Obtener el código | https://git-scm.com/downloads (no es necesario si se descarga el ZIP) |
| make | Cualquiera | Atajos de los comandos | Incluido en Linux y macOS. En Windows puede omitirse: la sección 7 indica el comando equivalente de cada atajo |
| Navegador | Chrome, Edge o Firefox recientes | Interfaz de usuario | Para el dictado por voz se recomienda Chrome o Edge |

No es necesario instalar Python por separado: uv descarga la versión 3.12 automáticamente. No se requiere ninguna
cuenta, clave de API ni conexión a servicios externos para la ejecución local.

Espacio en disco aproximado: 1.5 GB para el entorno virtual y 150 MB adicionales para el modelo de reconocimiento
de voz, que se descarga una sola vez en segundo plano.

### 2.2 Adicionalmente, para la ejecución en Databricks

| Componente | Detalle |
|---|---|
| Cuenta de Databricks Free Edition | https://www.databricks.com/learn/free-edition |
| Databricks CLI | Versión 0.250 o superior. Instalación: https://docs.databricks.com/dev-tools/cli/install.html |
| Permiso `CREATE CATALOG` | El propietario de un workspace de Free Edition dispone de él |

---

## 3. Ejecución local

Siga los pasos en el orden indicado. Todos los comandos se ejecutan desde la carpeta raíz del repositorio.

### Paso 1. Obtener el código

```bash
git clone https://github.com/lmrcolin/hardware-replacement-agent.git
cd hardware-replacement-agent
```

Si recibió el proyecto como archivo ZIP, descomprímalo y abra una terminal dentro de la carpeta resultante.

Los 33 documentos PDF de entrada (catálogo comercial y 32 datasheets) ya se encuentran en `data/raw/`. Si dispone de
ellos con la estructura del enunciado (`datos/pdfs/`), consulte la sección 6.3.

### Paso 2. Instalar las dependencias

```bash
make setup
```

Este comando crea el entorno virtual `.venv` con Python 3.12, instala todas las dependencias y registra los
controles automáticos de Git (si la carpeta no proviene de Git, este último paso se omite sin error). La primera
vez puede tardar algunos minutos.

Resultado esperado: el comando termina sin errores. Sin `make`, ejecute `uv sync`.

### Paso 3. Iniciar la aplicación

```bash
make app
```

Resultado esperado: la terminal muestra una línea similar a `Local URL: http://localhost:8501`. La primera carga
procesa los 33 PDFs en memoria y tarda unos segundos.

Sin `make`, ejecute: `uv run --extra voice --extra claude streamlit run app/streamlit_app.py`

### Paso 4. Abrir la interfaz

Abra en el navegador la dirección **http://localhost:8501**. Se mostrará la pantalla de inicio con el título
"¿Qué pieza necesitas reemplazar?", un campo de consulta, sugerencias de uso y el catálogo de las 11 piezas que
requieren reemplazo.

### Paso 5. Realizar una consulta

Escriba en el campo de consulta, por ejemplo, `Necesito reemplazar la E810-CQDA2`, y presione Enter. También puede
pulsar la sugerencia "Reemplazar la Intel E810-CQDA2" o cualquier tarjeta del catálogo.

Resultado esperado: tras unos segundos aparecen la pieza original (Descontinuada) y las dos opciones descritas en la
sección 1.2, con su comparación de especificaciones y sus citas. El apartado "Cómo lo resolvió el agente" muestra el
plan seguido y cada herramienta utilizada.

Otras consultas recomendadas para comprobar las capacidades del agente:

| Consulta | Comportamiento esperado |
|---|---|
| `¿y la más barata?` (después de la anterior) | Recuerda la pieza y ordena las opciones por precio: BCM57508 en primer lugar |
| `compárala con la BCM57508` | Compara ambas tarjetas especificación por especificación |
| `¿la MCX soporta RoCE v2?` | Responde "sí declara RoCE v2" con la cita del datasheet |
| `Necesito reemplazar la A100` | No recomienda sustituto (el factor de forma difiere) y ofrece la H100 como alternativa si se acepta ese cambio |
| `Necesito reemplazar la WUS4C6464DSP3X5` | Informa que no existe sustituto y explica por qué se descartó el único candidato |
| `Busco una tarjeta de red` | Pregunta por la velocidad requerida y ofrece botones con las opciones del catálogo |
| `Reemplazo para la E81O-CQDA2` (con la letra O) | Sugiere el part number correcto en lugar de suponerlo |

### Paso 6. Detener la aplicación

En la terminal donde se ejecuta, presione `Ctrl+C`.

---

## 4. Verificación de la instalación

### 4.1 Pruebas automáticas

```bash
make check
```

Ejecuta el análisis estático (ruff y mypy), la verificación de la dirección de dependencias entre capas
(import-linter) y la batería completa de pruebas.

Resultado esperado: `All checks passed!`, `Contracts: 2 kept, 0 broken` y una línea final que informa el número
de pruebas superadas, sin ninguna fallida. Las pruebas no modifican el historial de búsquedas del usuario ni utilizan claves de API.

### 4.2 Evaluación sobre el conjunto de referencia

```bash
make eval
```

Evalúa 32 casos verificados contra los PDFs y reescribe `evaluation/report.md`.

Resultado esperado: la línea `Puertas de seguridad: OK (todas en 0)` y las métricas de resolución, estado,
aclaración, acierto en la primera recomendación y nivel de compatibilidad en 1.00. El detalle se describe en la
sección 10.

### 4.3 Reproducción completa automatizada

```bash
scripts/reproduce_from_scratch.sh --local-only
```

Reconstruye todos los artefactos desde los PDFs y ejecuta las verificaciones locales en una sola orden.

---

## 5. Ejecución completa en Databricks Free Edition

En este modo los datos se leen en vivo desde tablas Delta de Unity Catalog, la búsqueda documental combina BM25 con
un índice vectorial de AI Search y el modelo de lenguaje es Llama 3.3 70B, servido por la Foundation Model API de
Databricks sin costo adicional.

### Paso 1. Autenticar la CLI de Databricks (una sola vez)

```bash
databricks auth login --host https://<su-workspace>.cloud.databricks.com
```

Sustituya `<su-workspace>` por el identificador de su workspace. Se abrirá el navegador para iniciar sesión; las
credenciales quedan guardadas en `~/.databrickscfg` y nunca dentro del repositorio.

### Paso 2. Validar y desplegar el proyecto

```bash
databricks bundle validate
databricks bundle deploy -t dev
```

El despliegue construye el paquete del proyecto y lo sincroniza con el workspace.

Resultado esperado: ambos comandos terminan sin errores.

### Paso 3. Ejecutar el pipeline de datos

```bash
databricks bundle run run_all -t dev
```

Duración aproximada: de 6 a 10 minutos. La primera vez se añaden cerca de 20 minutos mientras Databricks aprovisiona
el endpoint de AI Search. El job es idempotente: puede ejecutarse varias veces sin efectos indeseados.

El job ejecuta ocho tareas en cómputo serverless:

| Tarea | Función | Resultado |
|---|---|---|
| `setup` | Crea el catálogo `emerson_hw`, sus esquemas y volúmenes, y copia los 33 PDFs | `bronze.raw_files`, `bronze.libs` |
| `parse` | Extrae el texto de los PDFs con `ai_parse_document` (no repite el trabajo si ya existe) | `bronze.documents_parsed` |
| `extract_enrich` | Lee el catálogo, extrae las especificaciones y las cruza con el catálogo | `silver.*`, `gold.products` |
| `chunk_index` | Divide los datasheets en fragmentos con su origen | `gold.document_chunks` |
| `build_kg` | Construye el grafo de conocimiento | `gold.kg_nodes`, `gold.kg_edges` |
| `compat_matrix` | Calcula la compatibilidad de cada pieza no vendible | `gold.compat_matrix` |
| `export_artifacts` | Exporta los artefactos | `/Volumes/emerson_hw/gold/artifacts` |
| `ai_search` | Crea o sincroniza el endpoint `emerson-vs` y su índice vectorial | `gold.document_chunks_index` |

Resultado esperado: las ocho tareas terminan en estado `SUCCESS` y la última informa
`OK: emerson_hw.gold.document_chunks_index sincronizado con 126 filas en emerson-vs`.

### Paso 4. Comprobar las tablas (opcional)

| Tabla | Filas esperadas |
|---|---|
| `emerson_hw.bronze.documents_parsed` | 33 |
| `emerson_hw.silver.commercial` | 32 (21 ACTIVE, 6 DISCONTINUED, 2 EOL, 3 NRND) |
| `emerson_hw.silver.product_specifications` | 272 |
| `emerson_hw.gold.products` | 32 |
| `emerson_hw.gold.document_chunks` | 126 |
| `emerson_hw.gold.compat_matrix` | 30 |
| `emerson_hw.gold.kg_nodes` / `kg_edges` | 501 / 586 |

### Paso 5. Iniciar la aplicación conectada a Databricks

```bash
make app-databricks
```

Abra **http://localhost:8501**. La aplicación se ejecuta en su equipo, pero los datos, la búsqueda vectorial y el
modelo de lenguaje residen en Databricks.

Para evaluar en este modo los mismos 32 casos de la sección 4.2, ejecute `make eval-databricks` (no reescribe el
informe local).

### Paso 6. Confirmar que se utiliza Databricks

En la aplicación, abra **Ajustes** (icono de engrane, esquina superior derecha) y despliegue **Detalles técnicos**.
Deberá observar:

- Datos: `Databricks en vivo: emerson_hw.gold.* vía SQL warehouse ...`
- Búsqueda documental: `híbrida RRF: BM25 ... + AI Search ... en línea`
- Modelo de lenguaje: `databricks → template`

En cada respuesta, el apartado "Cómo lo resolvió el agente" indica qué modelo planificó y redactó. En el workspace de
Databricks, la actividad puede confirmarse en el historial de consultas del SQL warehouse, en las métricas del
serving endpoint de Llama y del endpoint `emerson-vs`, y mediante la tabla del sistema `system.billing.usage`.

### 5.1 Situaciones particulares

| Situación | Acción |
|---|---|
| Utiliza un perfil de la CLI con nombre | Añada `--profile <perfil>` a los comandos `databricks` y `PROFILE=<perfil>` a los comandos `make` |
| El workspace tiene más de un SQL warehouse | Defina `ADVISOR_DATABRICKS_WAREHOUSE_ID=<id>` antes de `make app-databricks` |
| Ya existe otro endpoint de AI Search (Free Edition permite uno) | Ejecute `databricks bundle run run_all -t dev --params ai_search=false`; la aplicación utilizará solo BM25 y lo indicará |
| Otra persona del equipo debe poder ejecutar `run_all` | El propietario del índice debe ejecutar ``GRANT ALL PRIVILEGES ON TABLE emerson_hw.gold.document_chunks_index TO `account users` `` y conceder `CAN_MANAGE` al grupo `users` sobre el endpoint `emerson-vs` |
| Desea trabajar en local con los artefactos generados en Databricks | Ejecute `scripts/reproduce_from_scratch.sh --pull-artifacts` |

---

## 6. Configuración opcional

### 6.1 Archivo de entorno

La aplicación funciona sin configuración. Para personalizarla, copie la plantilla y edite el archivo resultante:

```bash
cp .env.example .env
```

El archivo `.env` está excluido de Git y nunca debe incorporarse al repositorio.

### 6.2 Variables disponibles

| Variable | Valores | Efecto |
|---|---|---|
| `ADVISOR_LLM_PROVIDERS` | Lista separada por comas: `databricks`, `ollama`, `template` | Cadena de modelos de lenguaje. Por defecto, en local se utilizan plantillas deterministas |
| `ADVISOR_REPOSITORY_BACKEND` | `local`, `databricks_sql` | Origen de los datos: PDFs locales o tablas Delta |
| `ADVISOR_RETRIEVAL_BACKEND` | `bm25`, `ai_search`, `hybrid` | Motor de búsqueda documental |
| `ADVISOR_DATABRICKS_PROFILE` | Nombre de perfil | Perfil de la CLI de Databricks; vacío utiliza el perfil por defecto |
| `ADVISOR_DATABRICKS_WAREHOUSE_ID` | Identificador | SQL warehouse a utilizar si existe más de uno |
| `ADVISOR_PDF_DIR` | Ruta | Carpeta de PDFs para la ejecución local (por defecto `data/raw`) |
| `ANTHROPIC_API_KEY` | Clave | Habilita la opción de Claude (sección 6.4) |
| `ADVISOR_CLAUDE_MODEL` | Identificador de modelo | Modelo de Claude; por defecto `claude-haiku-5-5` |
| `ADVISOR_LLM_DEFAULT` | `ours`, `claude` | Modelo preseleccionado en Ajustes |
| `ADVISOR_WHISPER_MODEL` | `base`, `small` | Modelo de dictado por voz; por defecto `base` |
| `ADVISOR_SEARCH_LOG` | Ruta | Ubicación del historial de búsquedas (por defecto `.cache/advisor/searches.jsonl`, excluido de Git) |
| `ADVISOR_OLLAMA_HOST` | URL | Servidor de Ollama, si se utiliza |

### 6.3 Documentos con la estructura del enunciado

Si los PDFs se encuentran en `datos/pdfs/`, existen dos alternativas: copiarlos a `data/raw/` (necesario para el job
de Databricks) o, únicamente para la ejecución local, iniciar la aplicación con
`ADVISOR_PDF_DIR=datos/pdfs make app`.

### 6.4 Modelo de lenguaje Claude (opcional, con costo)

En **Ajustes > Modelo de lenguaje** puede elegirse entre "Nuestro LLM" (Llama 3.3 en Databricks, con plantillas de
respaldo) y "Claude (API key)". Para habilitar la segunda opción, defina `ANTHROPIC_API_KEY` en `.env`. El modelo por
defecto es `claude-haiku-5-5`, con un costo aproximado de 0.0008 USD por consulta. Mientras la clave no esté
configurada, la aplicación lo indica y responde con plantillas. En ambos casos la compatibilidad, los precios y las
existencias provienen exclusivamente de las herramientas deterministas y del catálogo.

### 6.5 Dictado y lectura en voz alta

El campo de consulta incluye un micrófono. La transcripción se realiza localmente con faster-whisper; el audio no
sale del equipo. El modelo (unos 145 MB) se descarga en segundo plano la primera vez y el micrófono aparece cuando
está listo. La opción **Ajustes > Leer las respuestas en voz alta** utiliza la voz del navegador. El navegador
solicitará permiso para usar el micrófono; acéptelo y utilice la dirección `http://localhost:8501`.

---

## 7. Referencia de comandos

| Atajo | Función | Comando equivalente sin make |
|---|---|---|
| `make setup` | Crea el entorno e instala las dependencias | `uv sync` |
| `make app` | Inicia la aplicación en modo local | `uv run --extra voice --extra claude streamlit run app/streamlit_app.py` |
| `make app-databricks` | Inicia la aplicación conectada a Databricks | Variables `ADVISOR_REPOSITORY_BACKEND=databricks_sql`, `ADVISOR_RETRIEVAL_BACKEND=hybrid` y `ADVISOR_LLM_PROVIDERS=databricks,template` más el comando de `make app` |
| `make check` | Análisis estático y pruebas | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run lint-imports` y `uv run pytest` |
| `make eval` | Evaluación sobre el conjunto de referencia | `uv run python -m evaluation.run_eval` |
| `make eval-databricks` | Evaluación con Databricks y Llama | Variables de `make app-databricks` más `uv run python -m evaluation.run_eval --retriever hybrid --llm configured --no-report` |
| `make pipeline-local` | Genera los artefactos en `artifacts/` (acelera el arranque de la aplicación) | `uv run advisor-pipeline` |
| `make excel` | Genera el análisis de costos en `cost/emerson_advisor_tco.xlsx` | `uv run python scripts/build_tco_excel.py` |
| `make format` | Aplica el formato de código | `uv run ruff format .` y `uv run ruff check --fix .` |

---

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `uv: command not found` | uv no está instalado o no está en el PATH | Instálelo según la sección 2.1 y abra una terminal nueva |
| `make: command not found` (Windows) | Windows no incluye make | Utilice los comandos equivalentes de la sección 7 |
| `Port 8501 is already in use` | Otra instancia de la aplicación sigue activa | Deténgala con `Ctrl+C` o inicie con `--server.port 8502` al final del comando de la sección 7 |
| El micrófono no aparece | El modelo de voz aún se descarga | Espere a que desaparezca el aviso "Preparando el reconocimiento de voz" en Ajustes |
| Error de permiso del micrófono | El navegador no autorizó el acceso | Use Chrome o Edge en `http://localhost:8501` y permita el micrófono desde el icono del candado |
| Ajustes indica "Claude no está listo" | Falta `ANTHROPIC_API_KEY` en `.env` | Configure la clave o utilice "Nuestro LLM" |
| `PERMISSION_DENIED` al ejecutar `run_all` | Falta `CREATE CATALOG` o permisos sobre `emerson_hw` | Ejecute el job con la cuenta propietaria del workspace o solicite los permisos al propietario |
| La tarea `ai_search` falla por permisos | El índice pertenece a otro usuario | Aplique el `GRANT` indicado en la sección 5.1 |
| `make app-databricks` indica que hay varios warehouses | El workspace tiene más de un SQL warehouse | Defina `ADVISOR_DATABRICKS_WAREHOUSE_ID` |
| La búsqueda indica que AI Search no está disponible | El índice se está sincronizando o no existe | La aplicación continúa con BM25; espere a que el índice figure como en línea |

---

## 9. Arquitectura

```
33 PDFs (data/raw) -> extracción de texto -> especificaciones con cita literal -> cruce con el catálogo
                                                   |
               fragmentos + BM25 / AI Search <-----+-----> grafo de conocimiento (NetworkX)
                                                   |
                                                   v
  agente: interpretación -> memoria -> plan (Llama o reglas) -> herramientas con guardián -> redacción -> verificación
```

- **Herramientas del agente:** identificar la pieza, buscar y validar sustitutos, buscar en el catálogo por
  requisitos, negociar un requisito cuando no hay resultados, consultar los datasheets, comparar productos y
  formular la pregunta que más reduce las opciones.
- **Guardián:** cada paso propuesto por el modelo de lenguaje se valida contra una política de reglas; los pasos
  inválidos se sustituyen y quedan registrados en "Cómo lo resolvió el agente".
- **Orden de las recomendaciones:** nivel de compatibilidad, cobertura de requisitos obligatorios y puntuación; las
  existencias solo desempatan.
- **Memoria de conversación:** permite seguimientos como "¿y la más barata?", "ya no necesito IPsec" o
  "compárala con la BCM57508".

Documentación detallada: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) y
[docs/COMPATIBILITY_ENGINE_DESIGN.md](docs/COMPATIBILITY_ENGINE_DESIGN.md).

---

## 10. Resultados de la evaluación

Conjunto de referencia de 32 casos verificados contra los PDFs (`evaluation/gold_set.yaml`):

| Métrica | Local (plantillas, BM25) | Databricks (Llama, búsqueda híbrida) |
|---|---|---|
| Resolución de la pieza, estado y aclaraciones | 1.00 | 1.00 |
| Acierto en la primera recomendación (hit@1) | 1.00 | 1.00 |
| Nivel de compatibilidad correcto | 1.00 | 1.00 |
| Recall@5 de la búsqueda documental | 0.88 | 1.00 |
| Recomendaciones prohibidas, no ACTIVE, precios o existencias distintos del catálogo, cifras no verificadas | 0 | 0 |

En las consultas descriptivas sin part number, la búsqueda híbrida alcanza un Recall@5 de 1.00, frente a 0.70 de
BM25 y 0.90 de AI Search por separado ([evaluation/report_hybrid.md](evaluation/report_hybrid.md)).

El conjunto de referencia es reducido y fue elaborado por el propio equipo; el detalle y sus limitaciones se
encuentran en [evaluation/report.md](evaluation/report.md). El análisis de costos (desarrollo, mantenimiento anual y
costo total de propiedad) se encuentra en `cost/emerson_advisor_tco.xlsx` y en
[docs/COST_MODEL.md](docs/COST_MODEL.md).

---

## 11. Limitaciones conocidas

- Cuatro datasheets se contradicen entre su texto descriptivo y su tabla de resumen (SN860, IR3555, Agilex 7 y
  BCM57508); se utiliza el valor del resumen, con su cita ([docs/DATA_INVENTORY.md](docs/DATA_INVENTORY.md)).
- `ai_parse_document` transcribió de forma incorrecta un part number del catálogo; por ello el catálogo se lee con un
  analizador determinista (ADR-012).
- El datasheet de la A100 menciona a la H100 como sucesora, pero su factor de forma es distinto; no se recomienda
  como reemplazo directo y solo se ofrece como alternativa condicionada.
- Los candidatos a los que les falta un dato crítico no se recomiendan; se presentan aparte como posibles, sujetos a
  la validación de un experto (ADR-013).
- Las respuestas se redactan en español aunque la consulta se formule en otro idioma.

---

## 12. Estructura del repositorio y documentación adicional

```
src/advisor/           lógica por capas (modelos, extracción, grafo, compatibilidad, agente, etc.)
config/                configuración, registro de especificaciones y reglas de compatibilidad
app/                   aplicación Streamlit (app/static/design.css contiene el sistema de diseño)
databricks/notebooks/  notebooks del pipeline; databricks.yml define el bundle y el job run_all
evaluation/            conjunto de referencia, conjunto ciego, métricas e informes
cost/                  análisis de costos (generado con make excel)
tests/                 pruebas de contratos, unitarias, de datos e integración
data/raw/              33 PDFs de entrada
docs/                  arquitectura, decisiones (ADR), contratos, plan de demostración y tareas
```

| Documento | Contenido |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Reglas del proyecto y guía para colaboradores |
| [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) | Registro de decisiones de arquitectura |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Esquemas de las tablas bronze, silver y gold |
| [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) | Capacidades de Databricks Free Edition probadas |
| [docs/DEMO_PLAN.md](docs/DEMO_PLAN.md) | Guion de la demostración |
