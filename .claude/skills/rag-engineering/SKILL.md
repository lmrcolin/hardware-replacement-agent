---
name: rag-engineering
description: Use when extracting text or tables from technical PDFs/datasheets, designing chunking, embeddings, BM25 or hybrid retrieval, reranking, citations, or evaluating retrieval quality. Guarantees every retrieved fact is traceable to document, page and chunk.
---

# RAG Engineering para documentación técnica

## Objetivo

Recuperar evidencia **verificable** para especificaciones y relaciones de sustitución.
Cada fragmento devuelto debe poder rastrearse hasta `document_id` → `page` → `chunk_id` → texto exacto.
La recuperación aporta candidatos y evidencias; **no decide compatibilidad** (eso es del motor determinista).

## Pipeline

1. **Ingesta:** registra el documento en `technical_documents` (`document_id` = hash SHA-256 del binario, `title`, `manufacturer`, `doc_type` ∈ {datasheet, manual, catalog, notice}, `revision`, `published_at`, `source_uri`, `is_synthetic`).
2. **Extracción:** `pypdf` para texto por página; `pdftotext -layout` como alternativa para tablas; OCR (`tesseract`) solo si la página no tiene capa de texto, marcando `extraction_method="ocr"` y una confianza menor.
3. **Limpieza:** normaliza espacios y guiones partidos; conserva símbolos técnicos (°, ±, Ω, µ, ½"). No traduzcas unidades en el texto: la normalización ocurre en el dato estructurado.
4. **Chunking:**
   - Unidad base: sección/página, nunca cruza documentos.
   - 300–600 tokens con solapamiento de 50–80; las tablas de especificaciones se mantienen enteras (una tabla = un chunk, con la cabecera repetida si se parte).
   - Metadatos por chunk: `document_id`, `page_start`, `page_end`, `section_title`, `chunk_index`, `char_start`, `char_end`, `part_numbers_mentioned[]`.
   - `chunk_id = f"{document_id[:12]}:{page_start}:{chunk_index}"`, estable entre ejecuciones.
5. **Indexación:**
   - **BM25** (local, por defecto): muy bueno para números de parte, siglas (HART, ATEX) y valores. Tokeniza preservando `ABC-123`, `M20x1.5`, `4-20mA`.
   - **Embeddings** (opcional): modelo local pequeño o Databricks Vector Search (índice Delta Sync sobre `gold.document_chunks`; Free Edition solo admite 1 endpoint).
   - **Híbrido:** fusiona con Reciprocal Rank Fusion: `score = Σ 1/(60 + rank_i)`.
6. **Filtro previo por metadatos:** fabricante, categoría y números de parte extraídos de la consulta reducen el espacio antes del ranking.
7. **Reranking (opcional):** cross-encoder local; mide si mejora el MRR antes de adoptarlo.
8. **Citas:** la respuesta solo puede afirmar lo que esté en un chunk devuelto. Formato: `[document_id p.N §chunk_id]`.

## Criterios de calidad

- Re-ejecutar la ingesta produce los mismos `chunk_id`.
- Cada chunk tiene `document_id` y página; ningún chunk sin origen.
- Búsqueda por número de parte exacto → el documento correcto en top-1.
- Métricas en golden set: Precision@K, Recall@K, MRR (ver skill `evaluation-testing`).
- Los registros sintéticos se marcan como tales también en el índice y en las citas.

## Ejemplo — contrato de recuperación

```python
class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    text: str
    score: float
    retriever: Literal["bm25", "vector", "hybrid"]
    is_synthetic: bool


class Retriever(Protocol):
    def search(
        self, query: str, *, top_k: int, filters: dict[str, str] | None = None
    ) -> list[RetrievedChunk]: ...
```

## Errores a evitar

- Chunking que parte una tabla de especificaciones y separa valores de su cabecera.
- Tokenizadores que destrozan números de parte (`ABC-123` → `abc`, `123`).
- Fiarse solo de embeddings para identificadores exactos.
- Perder el número de página al trocear.
- Citar un documento que no fue devuelto por el retriever ("citas fantasma").
- Usar el texto recuperado para *inferir* valores que no aparecen literalmente.
- Mezclar revisiones de una ficha técnica sin conservar `revision` y fecha.
