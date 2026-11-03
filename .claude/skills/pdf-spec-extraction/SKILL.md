---
name: pdf-spec-extraction
description: Parses the commercial catalog and datasheets, extracts normalized ProductSpecification values with Evidence and joins them with the catalog. Use when working on ingestion, parsing, extraction, enrichment, chunking or config/spec_registry.yaml.
---

# PDF parsing, spec extraction and catalog join

## Alcance
`src/advisor/{ingestion,parsing,extraction,enrichment,chunking}/`, `config/spec_registry.yaml`, `tests/data/`.

## Datos (ver docs/DATA_INVENTORY.md)
- Catálogo: 32 filas, 2 páginas, celdas multilínea (p. ej. "Measurement Computing (MCC)"); precio solo si ACTIVE.
- 32 datasheets de 1–2 páginas, por producto o **familia** (EPYC 9004, Agilex 7, iCE40, Artix-7, SAM D21).
- Nombres de archivo heterogéneos: no cruzar por nombre de archivo.

## Convenciones
- `document_id` = sha256 del binario; estable.
- Cada `ProductSpecification` lleva `Evidence(document_id, page, chunk_id?, quote)`; la cita es texto literal.
- Claves y unidades canónicas solo de `spec_registry.yaml`; convertir unidades (GB/s, W, MHz, bits, V…) y conservar el valor original en la cita.
- Valor no encontrado ⇒ ausente (no `0`, no "N/A" como string).
- Specs de familia ⇒ `Evidence.scope = "family"`.
- Join: part number exacto → normalizado (sin guiones/espacios, mayúsculas) → rapidfuzz sobre título/descripción con umbral; todo lo dudoso al `JoinReport`.
- Chunks: no cruzan documentos; metadata `document_id`, `page`, `section`, `part_numbers`.

## Contratos
`discover_documents`, `parse_document`, `parse_catalog`, `extract_product`, `join_catalog`, `chunk_document` (docs/MODULE_CONTRACTS.md).

## Pruebas
`tests/data/`: catálogo → 32 filas, estados 21/6/2/3 (ACTIVE/DISCONTINUED/EOL/NRND); 32 datasheets unidos; ninguna spec sin evidencia; `chunk_id` estable entre ejecuciones.

## Prohibido
Inventar specs o rellenar por analogía; tomar estado/precio del datasheet; modificar `data/raw/`; descargar modelos OCR sin autorización.
