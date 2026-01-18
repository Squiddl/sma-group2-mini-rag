# Technologie-Stack

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

**Modelle:**
- `claude-sonnet-4` - Empfohlen
- `claude-opus-4` - Höchste Qualität

**Vorteile:**
- Bessere Antwortqualität
- Kein lokales RAM benötigt
- Schnellere Antworten

**Links:**
- [Dokumentation](https://docs.anthropic.com/)

### OpenAI (Optional)

**Zweck:** Alternative Cloud LLM

**Modelle:**
- `gpt-4o`
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

## Deployment

### Docker & Docker Compose

**Services:**
```yaml
- frontend (nginx)
- backend (fastapi)
- qdrant (vector-db)
- ollama (llm)
- postgres (metadata)
```

**Volumes:**
- `qdrant_data`: Vector Storage
- `ollama_models`: LLM Models
- `postgres_data`: Database
- `uploads`: Dokumente

**Networks:**
- `app-network`: Internal Communication

---

## Model Comparison

### LLM Models

| Modell | RAM | GPU | Speed | Quality | Cost |
|--------|-----|-----|-------|---------|------|
| phi3:mini | 4GB | Optional | ⚡⚡⚡ | ⭐⭐ | Free |
| llama2 | 12GB | Empfohlen | ⚡⚡ | ⭐⭐⭐ | Free |
| mistral | 12GB | Empfohlen | ⚡⚡ | ⭐⭐⭐⭐ | Free |
| claude-sonnet-4 | 0GB | N/A | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | $3/Mtok |
| gpt-4o | 0GB | N/A | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | $2.5/Mtok |

### Embedding Models

| Modell | Dim | Context | Sprache | Performance |
|--------|-----|---------|---------|-------------|
| mxbai-de | 1024 | 512 | DE (optimiert) | ⭐⭐⭐⭐ |
| nomic-embed | 768 | 8192 | Multilingual | ⭐⭐⭐ |
| bge-m3 | 1024 | 8192 | Multilingual | ⭐⭐⭐⭐ |

---

## Performance-Benchmarks

**Document Processing:**
- PDF Upload: ~5s (10MB)
- Docling Parse: ~60-90s
- Chunking: ~2s
- Embedding: ~20-30s (100 chunks)
- Total: ~90-120s

**Query Processing:**
- Vector Search: <100ms
- Reranking: ~200ms
- LLM Generation: 2-10s (streaming)
- Total: ~3-11s

**System Requirements:**
- Minimal: 8GB RAM, 10GB Storage
- Empfohlen: 16GB RAM, 20GB Storage, GPU
- Production: 32GB RAM, 50GB Storage, GPU
