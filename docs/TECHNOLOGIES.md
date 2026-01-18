# Technologie-Stack
---

| Komponente              | Technologie              | Zweck                        |
|-------------------------|--------------------------|------------------------------|
| **Backend**             | FastAPI + Python 3.11    | REST API, async processing   |
| **Vector DB**           | Qdrant                   | Semantische Suche (1024-dim) |
| **Embeddings**          | mxbai-embed-de-large-v1  | Deutsche Textvektorisierung  |
| **LLM**                 | Ollama / Claude / OpenAI | Text-Generierung             |
| **Document Processing** | Docling                  | PDF-Extraktion mit Struktur  |
| **Reranker**            | BGE-reranker-v2-m3       | Relevanz-Scoring             |
| **Database**            | PostgreSQL               | Chat-History, Metadata       |


---
Detaillierte Übersicht der verwendeten Technologien und Modelle.

---

## Backend Framework

### FastAPI

**Zweck:** REST API Backend mit automatischer OpenAPI-Dokumentation

**Features:**
- Async/Await Support
- Automatische Validierung (Pydantic)
- OpenAPI/Swagger UI
- WebSocket & SSE Support
- Type Hints Integration

**Links:**
- [Dokumentation](https://fastapi.tiangolo.com/)
- [GitHub](https://github.com/tiangolo/fastapi)

---

## LLM Runtime

### Ollama (Default)

**Zweck:** Self-hosted LLM Platform

**Features:**
- Lokale Modell-Ausführung
- GPU-Beschleunigung (CUDA/ROCm)
- Model Management
- REST API
- Docker-Support

**Modelle:**
- `llama2` (7B) - Empfohlen
- `phi3:mini` (3.8B) - Schneller, weniger RAM
- `mistral` (7B) - Alternative

**Links:**
- [Website](https://ollama.com/)
- [Dokumentation](https://docs.ollama.com/)
- [API-Referenz](https://docs.ollama.com/api)

### Anthropic Claude (Optional)

**Zweck:** High-Quality Cloud LLM

**Vorteile:**
- Bessere Antwortqualität
- Kein lokales RAM benötigt
- Schnellere Antworten

**Links:**
- [Dokumentation](https://docs.anthropic.com/)

### OpenAI (Optional)

**Modelle:**
- `gpt-4-turbo`
- `gpt-3.5-turbo`

**Links:**
- [API-Referenz](https://platform.openai.com/docs/api-reference)

---

## Vector Database

### Qdrant

**Zweck:** High-Performance Vector Search

**Features:**
- 1024-dimensional Vektoren
- Cosine Similarity
- HNSW-Indexierung
- Metadata-Filtering
- REST & gRPC API
- Persistence

**Konfiguration:**
```yaml
collection_name: documents
vector_size: 1024
distance: Cosine
```

**Links:**
- [Website](https://qdrant.tech/)
- [Dokumentation](https://qdrant.tech/documentation/)
- [API-Referenz](https://api.qdrant.tech/api-reference)

---

## Document Processing

### Docling

**Zweck:** Intelligente PDF-Extraktion

**Features:**
- Struktur-Erhaltung (Überschriften, Listen)
- Tabellen-Extraktion
- Metadaten-Extraktion
- Layout-Analyse
- Multi-Column Support

**Output-Format:**
- Markdown mit Metadaten
- Strukturierte JSON
- Plain Text mit Positionen

**Links:**
- [GitHub](https://github.com/docling-project)
- [Server](https://github.com/docling-project/docling-serve)
- [Dokumentation](https://docling-project.github.io/docling/)

---

## Embedding Models

### mxbai-embed-de-large-v1

**Zweck:** Deutsche Text-Vektorisierung

**Spezifikationen:**
- Dimensionen: 1024
- Kontext: 512 Tokens
- Sprache: Deutsch (optimiert)
- Normalisiert: Ja (Cosine)

**Performance:**
- MTEB-Score: 60.2 (Deutsch)
- Batch-Size: 32
- GPU-fähig

**Use Cases:**
- Semantische Suche
- Document Similarity
- Clustering

**Links:**
- [HuggingFace](https://huggingface.co/mixedbread-ai/deepset-mxbai-embed-de-large-v1)

### nomic-embed-text (Alternative)

**Spezifikationen:**
- Dimensionen: 768
- Kontext: 8192 Tokens
- Sprache: Multilingual

**Links:**
- [Ollama](https://ollama.com/library/nomic-embed-text)
- [Blog](https://www.nomic.ai/blog/posts/nomic-embed-text-v1)

---

## Reranking

### BGE Reranker v2-m3

**Zweck:** Relevanz-Scoring via Cross-Encoder

**Spezifikationen:**
- Typ: Cross-Encoder (nicht Bi-Encoder)
- Sprache: Multilingual
- Input: Query + Document
- Output: Relevance Score (0-1)

**Workflow:**
1. Vector Search (Top 20)
2. Reranking (Top 5)
3. Filtered Results

**Performance:**
- NDCG@10: 0.89
- MRR: 0.87

**Links:**
- [HuggingFace](https://huggingface.co/BAAI/bge-reranker-v2-m3)

---

## Database

### PostgreSQL

**Zweck:** Relationale Datenbank für Metadaten

**Schema:**
- `documents`: Dokument-Metadaten
- `chats`: Chat-Sessions
- `messages`: Chat-History
- `sources`: Quellenangaben

**Features:**
- ACID-Transaktionen
- Full-Text Search (optional)
- JSON-Support

**Links:**
- [Dokumentation](https://www.postgresql.org/docs/)

---

## Integration

### Zotero API

**Zweck:** Academic Reference Management

**Features:**
- Library-Sync
- Metadaten-Import
- Attachment-Download
- Collection-Support

**Endpoints:**
- User Libraries
- Group Libraries
- Collections
- Items

**Links:**
- [Website](https://www.zotero.org/)
- [Support](https://www.zotero.org/support/)
- [API v3](https://www.zotero.org/support/dev/web_api/v3/start)

---

## Frontend

### Vanilla JavaScript + Nginx

**Zweck:** Minimalistisches Web-Interface

**Stack:**
- HTML5
- CSS3 (Custom, kein Framework)
- JavaScript (ES6+, kein Build)
- Nginx (Static Server + Reverse Proxy)

**Features:**
- Server-Sent Events (SSE)
- Streaming Responses
- Source Citations
- Chat History

---

