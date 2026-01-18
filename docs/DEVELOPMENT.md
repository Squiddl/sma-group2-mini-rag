# Entwicklung

Guidelines für Entwicklung, Testing und Contribution.

---

## Entwicklungs-Setup

### Lokale Entwicklung

```bash
# Repository klonen
git clone https://github.com/DuncanSARapp/academic-rag-python.git
cd academic-rag-python

# Python Virtual Environment
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Dependencies installieren
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dev-Tools

# Backend starten
uvicorn main:app --reload --port 8000
```

### Docker Development

```bash
# Services mit Hot-Reload
docker-compose -f docker-compose.dev.yml up

# Einzelner Service neu bauen
docker-compose up -d --build backend

# Logs verfolgen
docker-compose logs -f backend
```

---

## Projektstruktur

```
backend/
├── main.py                     # FastAPI App Entry Point
│
├── api/                        # REST Endpoints
│   ├── __init__.py
│   ├── chat.py                 # Chat-Management
│   ├── documents.py            # Document Upload/Delete
│   ├── ingest.py               # Processing Pipeline
│   ├── zotero.py               # Zotero Integration
│   └── health.py               # Health Check
│
├── core/                       # Core Components
│   ├── __init__.py
│   ├── embeddings.py           # Embedding Model
│   ├── llm.py                  # LLM Factory
│   ├── reranker.py             # Reranking Logic
│   ├── vector_store.py         # Qdrant Client
│   └── settings.py             # Configuration
│
├── services/                   # Business Logic
│   ├── rag/
│   │   ├── rag_service.py      # RAG Pipeline
│   │   └── prompt_templates.py # Prompts
│   ├── ingest/
│   │   ├── document_processor.py  # Docling Integration
│   │   ├── chunker.py              # Text Chunking
│   │   └── metadata_extractor.py  # Metadata Extraction
│   └── integrations/
│       └── zotero_client.py    # Zotero API Client
│
├── persistence/                # Database
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy Models
│   └── session.py              # DB Session
│
└── tests/                      # Tests
    ├── test_api.py
    ├── test_rag.py
    └── test_ingest.py
```

---

## Code-Style

### Python (PEP 8)

```python
# Type Hints verwenden
def embed_text(text: str, model: str) -> list[float]:
    """
    Embed text using specified model.
    
    Args:
        text: Input text
        model: Model identifier
        
    Returns:
        Vector representation
    """
    pass

# Async für I/O-bound Operations
async def query_llm(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
        return response.json()
```

### Naming Conventions

- **Funktionen/Methoden**: `snake_case`
- **Klassen**: `PascalCase`
- **Konstanten**: `UPPER_SNAKE_CASE`
- **Private**: `_leading_underscore`

---

## Testing

### Unit Tests

```bash
# Alle Tests ausführen
pytest

# Mit Coverage
pytest --cov=backend --cov-report=html

# Specific Test
pytest tests/test_rag.py::test_embedding
```

### Integration Tests

```bash
# Docker-Umgebung starten
docker-compose -f docker-compose.test.yml up -d

# Tests ausführen
pytest tests/integration/

# Aufräumen
docker-compose -f docker-compose.test.yml down -v
```

### Test-Struktur

```python
# tests/test_rag.py
import pytest
from backend.services.rag.rag_service import RAGService

@pytest.fixture
def rag_service():
    return RAGService(...)

def test_embedding(rag_service):
    vector = rag_service.embed("Test text")
    assert len(vector) == 1024
    assert all(isinstance(x, float) for x in vector)

@pytest.mark.asyncio
async def test_query_streaming(rag_service):
    async for chunk in rag_service.query_stream("Test?"):
        assert "content" in chunk
```

---

## API Development

### Neuen Endpoint hinzufügen

```python
# backend/api/new_feature.py
from fastapi import APIRouter, Depends
from backend.core.settings import get_settings

router = APIRouter(prefix="/new-feature", tags=["New Feature"])

@router.post("/")
async def create_feature(
    data: FeatureSchema,
    settings = Depends(get_settings)
):
    # Implementation
    return {"status": "created"}
```

```python
# backend/main.py
from backend.api import new_feature

app.include_router(new_feature.router)
```

### Request Validation

```python
# backend/models/schemas.py
from pydantic import BaseModel, Field, validator

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    chat_id: str | None = None
    top_k: int = Field(5, ge=1, le=20)
    
    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty")
        return v.strip()
```

---

## Debugging

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# In Code
logger.debug("Processing chunk %d/%d", i, total)
logger.info("Document uploaded: %s", doc_id)
logger.warning("Low relevance score: %.2f", score)
logger.error("Failed to connect to Qdrant", exc_info=True)
```

### Environment Variables

```bash
# .env
LOG_LEVEL=DEBUG
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### Remote Debugging (VS Code)

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "main:app",
                "--reload",
                "--port",
                "8000"
            ],
            "jinja": true,
            "cwd": "${workspaceFolder}/backend"
        }
    ]
}
```

---

## Contribution Guidelines

### Branch Strategy

```
main                    # Production-ready
├── develop             # Development
├── feature/xyz         # New features
├── bugfix/xyz          # Bug fixes
└── release/v1.x        # Release branches
```

### Commit Messages

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

**Beispiel:**
```
feat(rag): add reranking to query pipeline

- Integrate BGE reranker v2-m3
- Add rerank parameter to query endpoint
- Update relevance scoring

Closes #42
```

### Pull Request

1. Feature-Branch erstellen
2. Changes committen
3. Tests schreiben/aktualisieren
4. PR erstellen mit Beschreibung
5. Code Review abwarten
6. Merge nach Approval

---

## Performance Optimization

### Profiling

```bash
# cProfile
python -m cProfile -o output.prof main.py

# Visualisierung
pip install snakeviz
snakeviz output.prof
```

### Memory Profiling

```bash
pip install memory-profiler
python -m memory_profiler backend/services/rag/rag_service.py
```

### Async Best Practices

```python
# ❌ Blocking
def slow_function():
    time.sleep(5)
    return result

# ✅ Non-blocking
async def fast_function():
    await asyncio.sleep(5)
    return result

# ✅ Parallel Execution
async def process_batch(items):
    tasks = [process_item(item) for item in items]
    return await asyncio.gather(*tasks)
```

---

## Security

### Dependency Scanning

```bash
# Safety Check
pip install safety
safety check

# Bandit (Security Linter)
pip install bandit
bandit -r backend/
```

### Environment Variables

```python
# ❌ Hardcoded
API_KEY = "sk-1234567890"

# ✅ Environment
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    
    class Config:
        env_file = ".env"
```

---

## Documentation

### Docstrings (Google Style)

```python
def chunk_text(text: str, max_size: int = 500) -> list[str]:
    """
    Split text into semantic chunks.
    
    Args:
        text: Input text to chunk
        max_size: Maximum chunk size in characters
        
    Returns:
        List of text chunks
        
    Raises:
        ValueError: If text is empty
        
    Example:
        >>> chunks = chunk_text("Long text...", max_size=100)
        >>> len(chunks)
        5
    """
    pass
```

### API Documentation

Automatisch via FastAPI:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Roadmap

### v1.1 (Q1 2026)
- [ ] User Authentication
- [ ] Rate Limiting
- [ ] Advanced Search Filters

### v1.2 (Q2 2026)
- [ ] Multi-User Support
- [ ] Citation Export (BibTeX)
- [ ] Custom Chunking Strategies

### v2.0 (Q3 2026)
- [ ] Multi-Modal Support (Images)
- [ ] Graph RAG
- [ ] Fine-Tuning Interface
