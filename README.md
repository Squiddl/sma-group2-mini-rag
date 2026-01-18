# SMA Gruppe 2 - Mini-RAG-System

**Prüfungsleistung:** [SMA - Semantic Multimedia Analysis](https://moodle.hs-mannheim.de/mod/assign/view.php?id=298501)

---

## Gruppe 2 - Teilnehmer

| Name | E-Mail |
|------|--------|
| Roman Butuc | 2212814@stud.hs-mannheim.de |
| Duncan Rapp | |
| Daniel Kühn | |
| Joshua Neef | |
| Mustafa Khatib | |
| Thore Eichhorn | |

---

## Python-Implementierung: Vor- und Nachteile

### ✅ Vorteile
- **Rich Ecosystem**: Umfangreiche KI/ML-Bibliotheken (HuggingFace, LangChain, FastAPI)
- **Rapid Prototyping**: Schnelle Entwicklung durch dynamische Typisierung
- **Community Support**: Große Developer-Community für RAG/LLM-Anwendungen
- **Native Integration**: Direkte Anbindung an ML-Frameworks (PyTorch, TensorFlow)
- **Docker-Ready**: Einfache Containerisierung und Deployment

### ❌ Nachteile
- **Fehlende Abstraktion**: Monolithische Struktur ohne klare Service-Trennung
- **Mehraufwand**: Manuelle Dependency-Verwaltung statt Framework-Konventionen
- **Performance**: GIL-Limitierung bei CPU-intensiven Operationen
- **Type Safety**: Runtime-Fehler statt Compile-Time-Checks
- **Scalability**: Horizontales Scaling komplexer als mit microservice-orientierten Frameworks

---

## 📚 Dokumentation

Die vollständige technische Dokumentation finden Sie hier:

- **[Setup & Installation →](./docs/SETUP.md)** - Docker-Compose, Konfiguration, Quick Start
- **[Performance-Optimierung →](./docs/PERFORMANCE.md)** - Memory-Limits, GPU-Setup, Benchmarks (Windows/macOS/Linux)
- **[Architektur →](./docs/ARCHITECTURE.md)** - System-Design, Komponenten, RAG-Pipeline
- **[API-Referenz →](./docs/API.md)** - REST-Endpoints, Schemas, Beispiele
- **[Technologie-Stack →](./docs/TECHNOLOGIES.md)** - FastAPI, Qdrant, Docling, LLM-Modelle
- **[Entwicklung →](./docs/DEVELOPMENT.md)** - Projektstruktur, Testing, Contribution Guidelines

---

## 🚀 Quick Start

```bash
# Repository klonen
git clone https://github.com/DuncanSARapp/academic-rag-python.git
cd academic-rag-python

# Services starten
docker-compose up -d --build

# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

---

## Architecture Overview


![Chat Interface](docs/chat-interface.png)
*Document-based Q&A mit RAG-Pipeline, Vektorsuche und LLM-Integration*

```
Frontend (Nginx) → Backend (FastAPI) → Qdrant Vector DB
                                    → LLM API (Ollama/Anthropic)
                                    → Zotero Integration
```

**RAG-Pipeline:** Docling → Chunking → Embedding (mxbai-de) → Qdrant → Reranking → LLM

➡️ **Detaillierte Architektur:** Siehe [ARCHITECTURE.md](./docs/ARCHITECTURE.md)

---

## Technologie-Stack

| Komponente | Technologie | Zweck |
|------------|-------------|-------|
| **Backend** | FastAPI + Python 3.11 | REST API, async processing |
| **Vector DB** | Qdrant | Semantische Suche (1024-dim) |
| **Embeddings** | mxbai-embed-de-large-v1 | Deutsche Textvektorisierung |
| **LLM** | Ollama / Claude / OpenAI | Text-Generierung |
| **Document Processing** | Docling | PDF-Extraktion mit Struktur |
| **Reranker** | BGE-reranker-v2-m3 | Relevanz-Scoring |
| **Database** | PostgreSQL | Chat-History, Metadata |

➡️ **Vollständige Übersicht:** Siehe [TECHNOLOGIES.md](./docs/TECHNOLOGIES.md)

---

## Lizenz & Attribution

Basierend auf dem [n8n AI Starter Kit](https://github.com/n8n-io/self-hosted-ai-starter-kit)

© 2026 SMA Gruppe 2 - Hochschule Mannheim
