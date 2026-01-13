RAG Chat System
Docker-based RAG (Retrieval-Augmented Generation) system with parent-child chunking, local embeddings, Zotero integration, and API-based LLM integration.
Features

Multi-format document upload (PDF, DOCX, TXT, MD)
Zotero Library Integration (automatic paper sync)
Multiple persistent chats
RAG-based question answering with reranking
Parent-child chunking strategy
Web-based interface

Architecture
┌─────────────────────────────────────────────────────────────────┐
│                         User Browser                            │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP
                         ▼
                  ┌─────────────┐
                  │   Frontend  │
                  │  (Nginx)    │
                  │  Port 80    │
                  └──────┬──────┘
                         │ API Calls
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
RAG System Workflow
Phase 1: Indexierung (Dokument-Upload)
📄 PDF Upload / Zotero Sync
    ↓
🔄 Docling Converter
    • PDF → Strukturiertes Markdown
    • Fallback: PyPDF (bei libGL-Fehler)
    ↓
📋 Metadata Extraction
    • Titel, Autor, Seitenzahl
    • Optional: LLM-basierte Analyse
    ↓
✂️ Document Chunking (Parent-Child)
    • Parent: 2000 Tokens (Kontext)
    • Child: 400 Tokens (Retrieval)
    • Overlap: Konsistenz
    ↓
🔢 Embedding Generation
    • Batch-Processing (32 Chunks/Batch)
    • Model: mxbai-embed-large-v1
    • Output: 1024-dim Vektoren
    ↓
💾 Qdrant Vector Storage
    • Collection: doc_X
    • Scalar Quantization (Kompression)
    • Hybrid Search (Dense + Metadata)
Phase 2: Retrieval (User-Query)
❓ User Query
    ↓
🔢 Query Embedding
    • Gleicher Encoder wie Dokumente
    ↓
🔍 Vector Search (Qdrant)
    • Top-K: 20 Kandidaten
    • Cosine Similarity
    ↓
🎯 Reranking
    • Model: bge-reranker-v2-m3
    • Präzise Query-Chunk-Bewertung
    • Top-K: 6 beste Chunks
    ↓
📚 Context Assembly
    • Parent-Chunks laden (mehr Kontext)
    • Optional: Neighbor Expansion (±4 Chunks)
    ↓
🤖 LLM Generation
    • Provider: Claude/OpenAI/Ollama
    • Prompt: Query + Context
    • Stream Response
    ↓
✅ Antwort an User
Prerequisites

Docker and Docker Compose
LLM API key (OpenAI, Anthropic, or Ollama)
Optional: Zotero account with API key

Setup
1. Clone Repository
bashgit clone https://github.com/DuncanSARapp/SMA-Abgabe.git
cd SMA-Abgabe
2. Configure Environment
bashcp .env.example .env
Minimal Configuration (.env):
env# LLM Provider (required)
ANTHROPIC_API_KEY=sk-ant-...
# oder
OPENAI_API_KEY=sk-...

# Zotero (optional)
ZOTERO_LIBRARY_ID=your-library-id
ZOTERO_API_KEY=your-zotero-key
ZOTERO_LIBRARY_TYPE=user  # oder "group"
Erweiterte Konfiguration (optional):
env# Models (defaults in settings.py)
EMBEDDING_MODEL=mixedbread-ai/mxbai-embed-large-v1
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# LLM Settings
LLM_PROVIDER=anthropic  # anthropic, openai, ollama
LLM_MODEL=claude-sonnet-4-20250514
LLM_TEMPERATURE=0.0

# Retrieval
TOP_K_RETRIEVAL=20
TOP_K_RERANK=6

Hinweis: Alle Parameter mit Defaults in backend/config/settings.py müssen nicht in .env gesetzt werden.

3. Run Setup Script
bash./setup.sh
The setup.sh script validates prerequisites, creates a virtual environment, installs dependencies, validates Docker configuration, and starts all services.
4. Access Application
Frontend: http://localhost:80
API Docs: http://localhost:8000/docs