# Architektur

Detaillierte Beschreibung der System-Architektur und Komponenten.

---

## System-Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP
                         ▼
                  ┌─────────────┐
                  │   Frontend  │
                  │  (Nginx)    │
                  │  Port 3000  │
                  └──────┬──────┘
                         │ REST API
                         ▼
                  ┌─────────────┐
                  │   Backend   │
                  │  (FastAPI)  │
                  │  Port 8000  │
                  └──────┬──────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
 ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  Qdrant  │    │ LLM API  │    │  Zotero  │
 │Port 6333 │    │ (Remote) │    │   API    │
 └──────────┘    └──────────┘    └──────────┘
```

---

## RAG-Pipeline

Das System verarbeitet Dokumente in 4 Phasen:

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│                  │      │                  │      │                  │      │                  │
│     INGEST       │      │      EMBED       │      │     SEARCH       │      │    GENERATE      │
│                  │      │                  │      │                  │      │                  │
│    Document      │─────▶│    Sentence      │─────▶│     Vector       │─────▶│       LLM        │
│     Parsing      │      │   Embeddings     │      │   Similarity     │      │     Response     │
│                  │      │                  │      │                  │      │                  │
│  • Docling       │      │  • mxbai-de      │      │  • Qdrant        │      │  • Ollama        │
│  • Chunking      │      │  • 1024-dim      │      │  • Cosine        │      │  • Anthropic     │
│  • Metadata      │      │  • German        │      │  • Rerank        │      │  • Streaming     │
│                  │      │                  │      │                  │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘      └──────────────────┘
```

### Phase 1: Ingest (Dokumenten-Aufnahme)

**Komponenten:**
- **Docling**: PDF-Parsing mit Strukturerhaltung
- **Chunking**: Aufteilung in semantische Einheiten
- **Metadata Extraction**: Autor, Titel, Datum, Seitenzahlen

**Output:** Strukturierte Chunks mit Kontext

### Phase 2: Embed (Vektorisierung)

**Komponenten:**
- **mxbai-embed-de-large-v1**: Deutsche Embedding-Modell
- **Dimensionen**: 1024-dimensional
- **Normalisierung**: Cosine-Similarity-optimiert

**Output:** Vektor-Repräsentationen der Chunks

### Phase 3: Search (Vektorsuche)

**Komponenten:**
- **Qdrant**: High-Performance Vector DB
- **Similarity**: Cosine-Similarity
- **BGE Reranker**: Cross-Encoder für Relevanz-Scoring

**Output:** Top-K relevante Chunks

### Phase 4: Generate (LLM-Antwort)

**Komponenten:**
- **LLM**: Ollama / Claude / OpenAI
- **Streaming**: Server-Sent Events (SSE)
- **Context**: Relevante Chunks + Chat-History

**Output:** Generierte Antwort mit Quellenangaben

---

## Projektstruktur

```
sma-rag-python/
├── docker-compose.yml          # Orchestrierung
├── .env.example                # Konfiguration
│
├── backend/                    # FastAPI Application
│   ├── main.py                 # Entry Point
│   ├── api/                    # REST Endpoints
│   │   ├── chat.py
│   │   ├── documents.py
│   │   ├── ingest.py
│   │   ├── zotero.py
│   │   └── health.py
│   ├── core/                   # Core Components
│   │   ├── embeddings.py
│   │   ├── llm.py
│   │   ├── reranker.py
│   │   ├── vector_store.py
│   │   └── settings.py
│   ├── services/               # Business Logic
│   │   ├── rag/
│   │   ├── ingest/
│   │   └── integrations/
│   └── persistence/            # Database
│       └── models.py
│
├── frontend/                   # Web Interface
│   ├── index.html
│   ├── script.js
│   └── style.css
│
└── docs/                       # Documentation
    ├── SETUP.md
    ├── ARCHITECTURE.md
    ├── API.md
    └── TECHNOLOGIES.md
```

---

## Datenfluss

### Document Upload

```
User → Frontend → POST /documents
                    ↓
                 Backend
                    ↓
            File Validation
                    ↓
              Docling Parse
                    ↓
               Chunking
                    ↓
              Embedding
                    ↓
          Qdrant Storage
                    ↓
         PostgreSQL Metadata
```

### Query Processing

```
User → Frontend → POST /query/stream
                    ↓
                 Backend
                    ↓
           Embed Question
                    ↓
         Qdrant Vector Search
                    ↓
           BGE Reranking
                    ↓
         LLM Context Build
                    ↓
          Stream Response
                    ↓
              Frontend
                    ↓
                  User
```
