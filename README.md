# Emerson Replacement Advisor

Asistente agéntico para el Datathon MICAI 2026, Reto 1 (Emerson). Cuando una pieza de hardware está descontinuada
(DISCONTINUED), llegó a su fin de vida (EOL) o ya no se recomienda para diseños nuevos (NRND), el asistente la
identifica en el catálogo y recomienda sustitutos activos (ACTIVE) compatibles. Para cada uno indica precio,
unidades disponibles, condiciones de instalación y las citas de los datasheets que lo respaldan.

Este documento explica, paso a paso, cómo instalarlo, ejecutarlo y verificarlo en dos modos:

- **Local:** en tu equipo, sin cuentas ni claves. Es la forma más rápida de probarlo.
- **Databricks Free Edition:** datos en tablas Delta, búsqueda vectorial con AI Search y Llama 3.3 como modelo de
  lenguaje.

Cada vez que haga falta hacer algo fuera de la terminal (en la interfaz web de Databricks o en el archivo `.env`),
el paso lo indica de forma explícita con una nota **Acción manual**.

## Contenido

1. [Qué hace](#1-qué-hace)
2. [Requisitos](#2-requisitos)
3. [Ejecución local](#3-ejecución-local)
4. [Verificar la instalación](#4-verificar-la-instalación)
5. [Ejecución en Databricks Free Edition](#5-ejecución-en-databricks-free-edition)
6. [El archivo .env](#6-el-archivo-env)
7. [Funciones opcionales: Claude y voz](#7-funciones-opcionales-claude-y-voz)
8. [Referencia de comandos](#8-referencia-de-comandos)
9. [Solución de problemas](#9-solución-de-problemas)
10. [Arquitectura](#10-arquitectura)
11. [Resultados de la evaluación](#11-resultados-de-la-evaluación)
12. [Limitaciones conocidas](#12-limitaciones-conocidas)
13. [Estructura del repositorio](#13-estructura-del-repositorio)

---

## 1. Qué hace

### El problema

Cuando un cliente pide una pieza que ya no se vende, la venta se pierde salvo que alguien encuentre a tiempo un
sustituto activo, compatible y con existencias; hoy eso depende de expertos. El catálogo entregado tiene 32 piezas:
11 que ya no se venden (6 DISCONTINUED, 2 EOL y 3 NRND) y 21 ACTIVE, con 12,814,325.00 USD de inventario a precio de
catálogo. La meta es mover unos 4 millones de USD al año. El asistente convierte cada consulta por una pieza obsoleta
en una oferta vendible en segundos y, cuando no hay sustituto, lo dice y explica qué descartó y por qué.

### Resultado esperado del caso oficial

Consulta: *"Necesito una tarjeta de red 100 Gigabit Ethernet con soporte RDMA y offload de IPsec. Usábamos la Intel
E810 pero ya no la encuentro."*

- E810-CQDA2: DISCONTINUED desde el 1 de agosto de 2025.
- Opción 1: MCX75310AAS-NEAT (NVIDIA ConnectX-7 400GbE), 1,250.00 USD, 120 unidades, compatible con condiciones.
- Opción 2: BCM57508 (Broadcom 200GbE), 890.00 USD, 75 unidades, compatible con condiciones.
- Cada opción incluye la comparación de especificaciones, sus condiciones (por ejemplo, validar ópticas o usar
  breakout por tener más velocidad) y las citas del datasheet con número de página.

### Reglas que sigue

- **Fuente de verdad:** el catálogo comercial es la única fuente de estado, precio y existencias.
- **Compatibilidad:** la decide un motor de reglas determinista. Si una regla crítica falla, el candidato es
  incompatible. Si falta un dato crítico, no se recomienda y se muestra aparte para que lo valide un experto.
- **Qué se recomienda:** solo piezas ACTIVE. Las NRND aparecen como opciones con riesgo; las DISCONTINUED y EOL
  nunca.
- **Papel del modelo de lenguaje:** interpreta la consulta, propone qué herramientas usar y redacta la respuesta.
  No decide la compatibilidad ni inventa cifras: cada cifra del texto se verifica contra los datos antes de
  mostrarse.

---

## 2. Requisitos

### Para el modo local

| Componente | Para qué | Cómo instalarlo |
|---|---|---|
| uv (0.4 o superior) | Descarga Python 3.12 e instala las dependencias en un entorno aislado | Linux y macOS: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`. También: `pipx install uv` |
| Git | Descargar el código | https://git-scm.com/downloads (no hace falta si usas el ZIP) |
| make | Atajos de comandos | Ya viene en Linux y macOS. En Windows no es necesario: la sección 8 da el comando equivalente de cada atajo |
| Navegador | Usar la aplicación | Chrome, Edge o Firefox. Para dictar por voz, mejor Chrome o Edge |

No necesitas instalar Python por tu cuenta, ni crear cuentas o claves. Espacio en disco: unos 1.5 GB para el
entorno y 150 MB para el modelo de voz, que se descarga solo la primera vez.

Comprueba que uv quedó instalado (abre una terminal nueva después de instalarlo):

```bash
uv --version
```

### Para el modo Databricks (además de lo anterior)

| Componente | Detalle |
|---|---|
| Cuenta de Databricks Free Edition | Se crea gratis en https://www.databricks.com/learn/free-edition |
| Databricks CLI 0.250 o superior | Linux y macOS: `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh \| sh`. macOS con Homebrew: `brew tap databricks/tap && brew install databricks`. Windows: `winget install Databricks.DatabricksCLI`. Comprueba con `databricks --version` |
| Ser propietario del workspace | Para que el pipeline pueda crear el catálogo `emerson_hw`. En Free Edition, quien crea la cuenta ya lo es |

---

## 3. Ejecución local

Ejecuta todos los comandos desde la carpeta raíz del repositorio, en este orden.

### Paso 1. Descargar el código

```bash
git clone https://github.com/lmrcolin/hardware-replacement-agent.git
cd hardware-replacement-agent
```

Si tienes el proyecto en ZIP, descomprímelo y abre una terminal dentro de la carpeta.

Los 33 PDFs de entrada (catálogo comercial y 32 datasheets) ya vienen en `data/raw/`. Si los tienes con la estructura
del enunciado (`datos/pdfs/`), revisa la sección 6.4.

### Paso 2. Instalar dependencias

```bash
make setup
```

Crea el entorno `.venv` con Python 3.12, instala las dependencias y registra los controles de Git (si la carpeta no
viene de Git, ese último paso se omite sin error). La primera vez tarda algunos minutos.

Resultado esperado: termina sin errores. Sin `make`: `uv sync`.

**No hace falta crear el archivo `.env`** para el modo local: sin él, el asistente usa plantillas deterministas como
modelo de lenguaje y no se conecta a ningún servicio.

### Paso 3. Iniciar la aplicación

```bash
make app
```

Resultado esperado: la terminal muestra una línea como `Local URL: http://localhost:8501`. La primera carga procesa
los 33 PDFs en memoria y tarda unos segundos.

Sin `make`: `uv run --extra voice --extra claude streamlit run app/streamlit_app.py`

### Paso 4. Abrir la interfaz

Abre **http://localhost:8501** en el navegador. Debe aparecer:

- el título "¿Qué pieza necesitas reemplazar?"
- un campo de consulta y cuatro sugerencias
- el catálogo de las 11 piezas que necesitan reemplazo, con buscador y filtro por estado

### Paso 5. Hacer una consulta

Escribe `Necesito reemplazar la E810-CQDA2` y pulsa Enter. También puedes pulsar la sugerencia "Reemplazar la
Intel E810-CQDA2" o cualquier tarjeta del catálogo.

Resultado esperado: después de unos segundos aparecen la pieza original (Descontinuada) y las dos opciones de la
sección 1, con comparación de especificaciones y citas. El apartado "Cómo lo resolvió el agente" muestra el plan y
cada herramienta que usó.

Otras consultas para probar en la misma conversación:

| Consulta | Qué debe pasar |
|---|---|
| `¿y la más barata?` | Recuerda la pieza y pone primero la BCM57508 (la más barata) |
| `compárala con la BCM57508` | Compara las dos tarjetas especificación por especificación |
| `¿la MCX soporta RoCE v2?` | Responde que sí lo declara, con la cita del datasheet |

Y en conversaciones nuevas (botón "Nueva conversación" arriba a la derecha):

| Consulta | Qué debe pasar |
|---|---|
| `Necesito reemplazar la A100` | No recomienda sustituto (el factor de forma no coincide) y ofrece la H100 como alternativa si se acepta ese cambio |
| `Necesito reemplazar la WUS4C6464DSP3X5` | Dice que no hay sustituto y explica por qué descartó al único candidato |
| `Busco una tarjeta de red` | Pregunta qué velocidad necesitas y ofrece botones con las opciones del catálogo |
| `Reemplazo para la E81O-CQDA2` (con la letra O) | Sugiere el part number correcto en vez de darlo por hecho |

### Paso 6. Detener la aplicación

En la terminal donde corre, pulsa `Ctrl+C`.

### Opcional (Windows): dejar la aplicación siempre activa

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/app_service.ps1 -Action install   # o: make app-service
```

Registra la tarea programada `EmersonAdvisorApp`, que arranca la aplicación al iniciar sesión y la relanza si se cae.
Queda en **http://127.0.0.2:8601**, sin terminal abierta y sin depender de VS Code. Usa `127.0.0.2` porque VS Code Remote-SSH ocupa muchos puertos de `127.0.0.1`. Otras
acciones: `-Action status`, `restart`, `stop`, `logs` y `uninstall` (quita la tarea). El log está en
`%LOCALAPPDATA%\EmersonAdvisor\app.log`.

---

## 4. Verificar la instalación

### Pruebas automáticas

```bash
make check
```

Ejecuta el análisis estático (ruff y mypy), el control de dependencias entre capas (import-linter) y todas las
pruebas.

Resultado esperado: `All checks passed!`, `Contracts: 2 kept, 0 broken` y una línea final con el número de pruebas
superadas, sin fallos. Las pruebas no tocan tu historial de búsquedas ni usan claves de API.

### Evaluación sobre el conjunto de referencia

```bash
make eval
```

Evalúa 32 casos verificados contra los PDFs y actualiza `evaluation/report.md`.

Resultado esperado: `Puertas de seguridad: OK (todas en 0)` y resolución, estado, aclaración, primera recomendación
y nivel de compatibilidad en 1.00 (detalle en la sección 11).

### Reproducción completa automatizada

```bash
scripts/reproduce_from_scratch.sh --local-only
```

Reconstruye todos los artefactos desde los PDFs y ejecuta las verificaciones locales con un solo comando.

---

## 5. Ejecución en Databricks Free Edition

En este modo los datos se leen en vivo desde tablas Delta de Unity Catalog. La búsqueda documental combina BM25 con
un índice vectorial de AI Search, y el modelo de lenguaje es Llama 3.3 70B (Foundation Model API de Databricks, sin
costo adicional).

### Paso 1. Crear la cuenta y obtener la URL del workspace

> **Acción manual (Databricks):**
> 1. Crea tu cuenta en https://www.databricks.com/learn/free-edition e inicia sesión.
> 2. Copia la dirección que aparece en la barra del navegador. Es la URL de tu workspace y tiene esta forma:
>    `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`. La necesitas en el paso siguiente.
> 3. En el menú lateral, entra a **SQL Warehouses** y confirma que existe un warehouse (Free Edition crea uno
>    llamado "Serverless Starter Warehouse"). No hace falta iniciarlo: se enciende solo cuando se usa.

### Paso 2. Conectar la CLI con tu workspace (una sola vez)

```bash
databricks auth login --host https://dbc-xxxxxxxx-xxxx.cloud.databricks.com --profile DEFAULT
```

Sustituye la URL por la de tu workspace y deja `--profile DEFAULT` tal cual: así todos los comandos siguientes
encuentran la sesión sin indicar nada más.

- Se abre el navegador para iniciar sesión; autoriza el acceso.
- La sesión queda guardada en `~/.databrickscfg`, fuera del repositorio. No hay que copiar ningún token al proyecto.

Comprueba la conexión:

```bash
databricks current-user me
```

Debe mostrar tu usuario.

Si ya usas el perfil `DEFAULT` para otro workspace, elige otro nombre:
`databricks auth login --host <url> --profile <nombre>`. A partir de ahí, añade `--profile <nombre>` a todos los
comandos `databricks` y `PROFILE=<nombre>` a los comandos `make` de esta sección.

### Paso 3. Validar y desplegar el proyecto

```bash
databricks bundle validate
databricks bundle deploy -t dev
```

El despliegue construye el paquete del proyecto (por eso uv debe estar instalado) y lo sube a tu workspace.

Resultado esperado: ambos comandos terminan sin errores. No hace falta cambiar nada en `databricks.yml`.

### Paso 4. Ejecutar el pipeline de datos

```bash
databricks bundle run run_all -t dev
```

Duración: entre 6 y 10 minutos. La primera vez se suman unos 20 minutos mientras Databricks prepara el endpoint de AI
Search. El comando espera a que termine e imprime el resultado. Puedes ejecutarlo de nuevo sin problema: no duplica
datos.

Para seguir el avance en la interfaz web, entra a **Jobs & Pipelines** y abre el job `[dev <tu usuario>] run_all`.

Las ocho tareas del job:

| Tarea | Qué hace | Resultado |
|---|---|---|
| `setup` | Crea el catálogo `emerson_hw` con sus esquemas y volúmenes, y copia los 33 PDFs | `bronze.raw_files`, `bronze.libs` |
| `parse` | Extrae el texto de los PDFs con `ai_parse_document` (no lo repite si ya existe) | `bronze.documents_parsed` |
| `extract_enrich` | Lee el catálogo, extrae las especificaciones y las cruza | `silver.*`, `gold.products` |
| `chunk_index` | Divide los datasheets en fragmentos con su origen | `gold.document_chunks` |
| `build_kg` | Construye el grafo de conocimiento | `gold.kg_nodes`, `gold.kg_edges` |
| `compat_matrix` | Calcula la compatibilidad de cada pieza que ya no se vende | `gold.compat_matrix` |
| `export_artifacts` | Exporta los artefactos | `/Volumes/emerson_hw/gold/artifacts` |
| `ai_search` | Crea o sincroniza el endpoint `emerson-vs` y su índice vectorial | `gold.document_chunks_index` |

Resultado esperado: las ocho tareas en `SUCCESS`, y la última imprime
`OK: emerson_hw.gold.document_chunks_index sincronizado con 126 filas en emerson-vs`.

### Paso 5. Comprobar las tablas (opcional)

> **Acción manual (Databricks):** en **SQL Editor**, ejecuta por ejemplo
> `SELECT count(*) FROM emerson_hw.gold.products;`. También puedes revisar las tablas en **Catalog > emerson_hw**.

| Tabla | Filas esperadas |
|---|---|
| `emerson_hw.bronze.documents_parsed` | 33 |
| `emerson_hw.silver.commercial` | 32 (21 ACTIVE, 6 DISCONTINUED, 2 EOL, 3 NRND) |
| `emerson_hw.silver.product_specifications` | 272 |
| `emerson_hw.gold.products` | 32 |
| `emerson_hw.gold.document_chunks` | 126 |
| `emerson_hw.gold.compat_matrix` | 30 |
| `emerson_hw.gold.kg_nodes` / `kg_edges` | 501 / 586 |

### Paso 6. Iniciar la aplicación conectada a Databricks

```bash
make app-databricks
```

Abre **http://localhost:8501**. La aplicación corre en tu equipo, pero los datos, la búsqueda vectorial y el modelo
de lenguaje están en Databricks.

**No hace falta tocar el `.env`** para este modo: `make app-databricks` ya activa los datos de Databricks, la
búsqueda híbrida y Llama. Solo hay dos casos en los que sí:

| Caso | Qué añadir al `.env` |
|---|---|
| Usaste un perfil con nombre en el paso 2 | `ADVISOR_DATABRICKS_PROFILE=<nombre>` (o ejecuta `make app-databricks PROFILE=<nombre>`) |
| Tu workspace tiene más de un SQL warehouse (la aplicación lo avisa con el mensaje "define ADVISOR_DATABRICKS_WAREHOUSE_ID") | `ADVISOR_DATABRICKS_WAREHOUSE_ID=<id>` |

> **Acción manual (Databricks), solo si necesitas el ID del warehouse:** en **SQL Warehouses**, abre el warehouse y
> entra a **Connection details**. El ID es la última parte del campo **HTTP path**
> (`/sql/1.0/warehouses/<id>`).

Para evaluar en este modo los mismos 32 casos de la sección 4, ejecuta `make eval-databricks` (no modifica el informe
local).

### Paso 7. Confirmar que se está usando Databricks

En la aplicación, abre **Ajustes** (el engrane de arriba a la derecha) y despliega **Detalles técnicos**. Debe
aparecer:

- Datos: `Databricks en vivo: emerson_hw.gold.* vía SQL warehouse ...`
- Búsqueda documental: `híbrida RRF: BM25 ... + AI Search ... en línea`
- Modelo de lenguaje: `databricks → template`

En cada respuesta, el apartado "Cómo lo resolvió el agente" indica qué modelo hizo el plan y la redacción.

> **Acción manual (Databricks), si quieres verlo del lado de la plataforma:**
> - **SQL Warehouses > (tu warehouse) > Query History:** aparecen las lecturas de `emerson_hw.gold.*`.
> - **Serving > databricks-meta-llama-3-3-70b-instruct:** las peticiones aumentan con cada consulta.
> - **Compute > Vector Search > emerson-vs:** muestra las consultas al índice.
> - **SQL Editor:** `SELECT * FROM system.billing.usage ORDER BY usage_date DESC` muestra el consumo.

### Casos especiales

| Situación | Qué hacer |
|---|---|
| Ya existe otro endpoint de AI Search en el workspace (Free Edition solo permite uno) | Ejecuta `databricks bundle run run_all -t dev --params ai_search=false`. La aplicación usará solo BM25 y lo indicará en Ajustes |
| Otra persona del equipo también va a ejecutar `run_all` en el mismo workspace | **Acción manual (Databricks):** quien creó el índice debe ejecutar en el SQL Editor: ``GRANT ALL PRIVILEGES ON TABLE emerson_hw.gold.document_chunks_index TO `account users`;``. Además, en **Compute > Vector Search > emerson-vs > Permissions**, debe dar **Can manage** al grupo `users`. Si el índice se borra y se vuelve a crear, hay que repetirlo |
| Otra persona del equipo necesita leer las tablas | **Acción manual (Databricks):** el propietario del catálogo ejecuta en el SQL Editor: ``GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG emerson_hw TO `account users`;`` |
| Quieres trabajar en local con los artefactos generados en Databricks | `scripts/reproduce_from_scratch.sh --pull-artifacts` |
| Evitar dos ejecuciones simultáneas de `run_all` | El job ya lo impide para un mismo usuario; si son dos personas, conviene coordinarse para no sincronizar el índice a la vez |

---

## 6. El archivo .env

### 6.1 ¿Lo necesito?

| Modo | ¿Hace falta `.env`? |
|---|---|
| Local (`make app`) | No |
| Databricks (`make app-databricks`) | No, salvo un perfil con nombre o varios warehouses (sección 5, paso 6) |
| Usar Claude como modelo de lenguaje | Sí: `ANTHROPIC_API_KEY` (sección 7.1) |

### 6.2 Cómo crearlo

```bash
cp .env.example .env
```

Después edítalo con cualquier editor de texto. Cada línea tiene la forma `VARIABLE=valor`, sin espacios alrededor
del `=` ni comillas. Las líneas que empiezan con `#` se ignoran.

**Importante:** `.env` está excluido de Git. Nunca lo subas al repositorio ni compartas su contenido, porque puede
contener claves.

### 6.3 Variables disponibles

| Variable | Valores | Para qué sirve |
|---|---|---|
| `ADVISOR_DATABRICKS_PROFILE` | Nombre de perfil | Perfil de la CLI de Databricks. Vacío = perfil por defecto |
| `ADVISOR_DATABRICKS_WAREHOUSE_ID` | ID del warehouse | Solo si el workspace tiene más de uno |
| `ANTHROPIC_API_KEY` | Clave de Anthropic | Activa la opción Claude (sección 7.1) |
| `ADVISOR_LLM_DEFAULT` | `ours` o `claude` | Modelo que aparece seleccionado al abrir la aplicación |
| `ADVISOR_CLAUDE_MODEL` | Identificador de modelo | Modelo de Claude. Por defecto `claude-haiku-5-5` |
| `ADVISOR_LLM_PROVIDERS` | `databricks`, `ollama`, `template` separados por comas | Orden de los modelos de lenguaje. En local, por defecto, solo plantillas |
| `ADVISOR_REPOSITORY_BACKEND` | `local` o `databricks_sql` | De dónde leer los datos (lo fija `make app-databricks`) |
| `ADVISOR_RETRIEVAL_BACKEND` | `bm25`, `ai_search` o `hybrid` | Motor de búsqueda documental (lo fija `make app-databricks`) |
| `ADVISOR_PDF_DIR` | Ruta | Carpeta de PDFs en modo local. Por defecto `data/raw` |
| `ADVISOR_WHISPER_MODEL` | `base` o `small` | Modelo de dictado. `small` es más preciso pero más lento |
| `ADVISOR_SEARCH_LOG` | Ruta | Dónde se guarda el historial de búsquedas. Por defecto `.cache/advisor/searches.jsonl` |
| `ADVISOR_OLLAMA_HOST` | URL | Servidor de Ollama, si lo usas |

### 6.4 PDFs con la estructura del enunciado

Si tus PDFs están en `datos/pdfs/` y no en `data/raw/`:

- **Para Databricks:** cópialos a `data/raw/` antes del paso 3 de la sección 5. El pipeline los toma de ahí.
- **Solo para el modo local:** añade `ADVISOR_PDF_DIR=datos/pdfs` al `.env`, o ejecuta
  `ADVISOR_PDF_DIR=datos/pdfs make app`.

---

## 7. Funciones opcionales: Claude y voz

### 7.1 Claude como modelo de lenguaje (con costo)

En **Ajustes > Modelo de lenguaje** puedes elegir entre "Nuestro LLM" (Llama 3.3 en Databricks, con plantillas de
respaldo) y "Claude (API key)".

> **Acción manual (.env):**
> 1. Crea una clave en https://console.anthropic.com, en la sección **API Keys**.
> 2. Añade al `.env`: `ANTHROPIC_API_KEY=sk-ant-...` (tu clave completa).
> 3. Opcional: añade `ADVISOR_LLM_DEFAULT=claude` para que Claude aparezca seleccionado al abrir la aplicación.
> 4. Reinicia la aplicación (`Ctrl+C` y de nuevo `make app` o `make app-databricks`).

Modelo por defecto: `claude-haiku-5-5`, con un costo aproximado de 0.0008 USD por consulta. Mientras falte la clave,
Ajustes lo indica y el asistente responde con plantillas. Con cualquier modelo, la compatibilidad, los precios y las
existencias salen solo de las herramientas deterministas y del catálogo.

### 7.2 Dictado y lectura en voz alta

- **Dictado:** el campo de consulta tiene un micrófono. La transcripción se hace en tu equipo con faster-whisper y el
  audio no sale de él.
- **Modelo de voz:** unos 145 MB, se descarga en segundo plano la primera vez. El micrófono aparece cuando está listo
  (mientras tanto, Ajustes muestra "Preparando el reconocimiento de voz").
- **Lectura en voz alta:** **Ajustes > Leer las respuestas en voz alta** usa la voz del navegador.
- **Permiso del micrófono:** el navegador lo pide la primera vez; acéptalo. Usa la dirección `http://localhost:8501`,
  porque los navegadores bloquean el micrófono en direcciones de red como `http://192.168...`.

---

## 8. Referencia de comandos

| Atajo | Qué hace | Equivalente sin make |
|---|---|---|
| `make setup` | Crea el entorno e instala dependencias | `uv sync` |
| `make app` | Inicia la aplicación en modo local | `uv run --extra voice --extra claude streamlit run app/streamlit_app.py` |
| `make app-databricks` | Inicia la aplicación conectada a Databricks | Define `ADVISOR_REPOSITORY_BACKEND=databricks_sql`, `ADVISOR_RETRIEVAL_BACKEND=hybrid` y `ADVISOR_LLM_PROVIDERS=databricks,template`, y ejecuta el comando de `make app` |
| `make check` | Análisis estático y pruebas | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest` |
| `make eval` | Evaluación sobre el conjunto de referencia | `uv run python -m evaluation.run_eval` |
| `make eval-databricks` | Evaluación con Databricks y Llama | Las variables de `make app-databricks` y `uv run python -m evaluation.run_eval --retriever hybrid --llm configured --no-report` |
| `make pipeline-local` | Genera los artefactos en `artifacts/` (acelera el arranque de la aplicación) | `uv run advisor-pipeline` |
| `make excel` | Genera el análisis de costos en `cost/emerson_advisor_tco.xlsx` | `uv run python scripts/build_tco_excel.py` |
| `make format` | Da formato al código | `uv run ruff format .` y `uv run ruff check --fix .` |

---

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `uv: command not found` | uv no está instalado o la terminal no lo ve todavía | Instálalo (sección 2) y abre una terminal nueva |
| `make: command not found` (Windows) | Windows no trae make | Usa los equivalentes de la sección 8 |
| `localhost:8501` se queda cargando y nunca abre | VS Code Remote-SSH reenvía puertos del servidor remoto (8501, 8601...) en `127.0.0.1` y atrapa la conexión | Abre `http://[::1]:8501`, detén el reenvío en el panel **Ports** de VS Code, o usa la aplicación siempre activa en `http://127.0.0.2:8601` (sección 3, paso 6) |
| `Port 8501 is already in use` | Ya hay otra instancia de la aplicación abierta | Ciérrala con `Ctrl+C`, o añade `--server.port 8502` al final del comando de la sección 8 y abre `http://localhost:8502` |
| La primera carga tarda | Se están procesando los 33 PDFs | Espera unos segundos; para acelerar los arranques siguientes, ejecuta `make pipeline-local` una vez |
| No aparece el micrófono | El modelo de voz aún se está descargando | Espera a que en Ajustes desaparezca "Preparando el reconocimiento de voz" |
| Error de permiso del micrófono | El navegador no dio acceso | Usa Chrome o Edge en `http://localhost:8501` y permite el micrófono desde el icono del candado de la barra de direcciones |
| Ajustes dice "Claude no está listo" | Falta `ANTHROPIC_API_KEY` en `.env`, o no reiniciaste la aplicación | Revisa la sección 7.1 y reinicia |
| `databricks: command not found` | La CLI no está instalada | Instálala (sección 2) |
| `PERMISSION_DENIED` o `CREATE CATALOG` al ejecutar `run_all` | La cuenta no es propietaria del workspace | Ejecuta el job con la cuenta propietaria o pide los permisos (sección 5, casos especiales) |
| La tarea `ai_search` falla por permisos | El índice lo creó otra persona | Aplica el `GRANT` de la sección 5, casos especiales |
| La tarea `ai_search` falla porque ya hay otro endpoint | Free Edition solo permite un endpoint de AI Search | Ejecuta `run_all` con `--params ai_search=false` |
| `define ADVISOR_DATABRICKS_WAREHOUSE_ID` | El workspace tiene más de un SQL warehouse | Añade el ID al `.env` (sección 5, paso 6) |
| Ajustes indica que AI Search no está disponible | El índice se está sincronizando o no existe | La aplicación sigue funcionando con BM25; espera a que el índice aparezca en línea |

---

## 10. Arquitectura

```
33 PDFs (data/raw) -> extracción de texto -> especificaciones con cita literal -> cruce con el catálogo
                                                   |
               fragmentos + BM25 / AI Search <-----+-----> grafo de conocimiento (NetworkX)
                                                   |
                                                   v
  agente: interpretación -> memoria -> plan (Llama o reglas) -> herramientas con guardián -> redacción -> verificación
```

- **Herramientas del agente:**
  - identificar la pieza
  - buscar y validar sustitutos
  - buscar en el catálogo por requisitos
  - negociar un requisito cuando no hay resultados
  - consultar los datasheets
  - comparar productos
  - hacer la pregunta que más reduce las opciones
- **Guardián:** cada paso que propone el modelo de lenguaje se valida contra una política de reglas. Los pasos
  inválidos se reemplazan y quedan registrados en "Cómo lo resolvió el agente".
- **Orden de las recomendaciones:** nivel de compatibilidad, cobertura de requisitos obligatorios y puntuación; las
  existencias solo desempatan.
- **Memoria:** permite seguimientos como "¿y la más barata?", "ya no necesito IPsec" o "compárala con la BCM57508".

Más detalle: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) y
[docs/COMPATIBILITY_ENGINE_DESIGN.md](docs/COMPATIBILITY_ENGINE_DESIGN.md).

---

## 11. Resultados de la evaluación

Conjunto de referencia de 32 casos verificados contra los PDFs (`evaluation/gold_set.yaml`):

| Métrica | Local (plantillas, BM25) | Databricks (Llama, búsqueda híbrida) |
|---|---|---|
| Resolución de la pieza, estado y aclaraciones | 1.00 | 1.00 |
| Acierto en la primera recomendación (hit@1) | 1.00 | 1.00 |
| Nivel de compatibilidad correcto | 1.00 | 1.00 |
| Recall@5 de la búsqueda documental | 0.88 | 1.00 |
| Recomendaciones prohibidas o no ACTIVE, precios o existencias distintos del catálogo, cifras no verificadas | 0 | 0 |

En consultas descriptivas sin part number, la búsqueda híbrida llega a un Recall@5 de 1.00, frente a 0.70 de BM25 y
0.90 de AI Search por separado ([evaluation/report_hybrid.md](evaluation/report_hybrid.md)).

El conjunto de referencia es pequeño y lo elaboró el propio equipo; el detalle y sus limitaciones están en
[evaluation/report.md](evaluation/report.md). El análisis de costos (desarrollo, mantenimiento anual y TCO) está en
`cost/emerson_advisor_tco.xlsx` y en [docs/COST_MODEL.md](docs/COST_MODEL.md).

---

## 12. Limitaciones conocidas

- **Datasheets contradictorios:** cuatro se contradicen entre su texto y su tabla de resumen (SN860, IR3555,
  Agilex 7 y BCM57508). Se usa el valor del resumen, con su cita ([docs/DATA_INVENTORY.md](docs/DATA_INVENTORY.md)).
- **Lectura del catálogo:** `ai_parse_document` transcribió mal un part number del catálogo, así que el catálogo se
  lee con un analizador determinista (ADR-012).
- **A100 y H100:** el datasheet de la A100 menciona a la H100 como sucesora, pero su factor de forma es distinto. No
  se recomienda como reemplazo directo; solo aparece como alternativa condicionada.
- **Datos críticos faltantes:** los candidatos a los que les falta uno no se recomiendan; se muestran aparte como
  posibles, a validar por un experto (ADR-013).
- **Idioma:** las respuestas se redactan en español aunque la consulta llegue en otro idioma.

---

## 13. Estructura del repositorio

```
src/advisor/           lógica por capas (modelos, extracción, grafo, compatibilidad, agente, etc.)
config/                configuración, registro de especificaciones y reglas de compatibilidad
app/                   aplicación Streamlit (app/static/design.css contiene el sistema de diseño)
databricks/notebooks/  notebooks del pipeline; databricks.yml define el bundle y el job run_all
evaluation/            conjunto de referencia, conjunto ciego, métricas e informes
cost/                  análisis de costos (se genera con make excel)
tests/                 pruebas de contratos, unitarias, de datos e integración
data/raw/              33 PDFs de entrada
docs/                  arquitectura, decisiones (ADR), contratos, plan de demo y tareas
```

| Documento | Contenido |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Reglas del proyecto y guía para colaboradores |
| [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) | Registro de decisiones de arquitectura |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Esquemas de las tablas bronze, silver y gold |
| [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) | Capacidades de Databricks Free Edition probadas |
| [docs/DEMO_PLAN.md](docs/DEMO_PLAN.md) | Guion de la demo |
