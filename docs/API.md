# API-Referenz

REST-API Dokumentation für das RAG-System.

---

## Base URL

```
http://localhost:8000
```

**Interactive Docs:** http://localhost:8000/docs (Swagger UI)

---

## Endpoints

### Health Check

#### `GET /health`

System-Status prüfen.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-18T10:30:00Z",
  "services": {
    "qdrant": "connected",
    "llm": "available"
  }
}
```

---

### Documents

#### `POST /documents`

Dokument hochladen und verarbeiten.

**Request:**
```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@document.pdf" \
  -F "metadata={\"author\":\"Max Mustermann\"}"
```

**Response:**
```json
{
  "document_id": "doc_123",
  "filename": "document.pdf",
  "status": "processing",
  "processing_url": "/documents/doc_123/processing-stream"
}
```

#### `GET /documents/{id}/processing-stream`

Processing-Status als Server-Sent Events (SSE).

**Response (SSE):**
```
data: {"status": "parsing", "progress": 0.3}

data: {"status": "chunking", "progress": 0.6}

data: {"status": "embedding", "progress": 0.9}

data: {"status": "completed", "chunks": 42}
```

#### `GET /documents`

Liste aller Dokumente.

**Response:**
```json
{
  "documents": [
    {
      "id": "doc_123",
      "filename": "document.pdf",
      "status": "completed",
      "chunks": 42,
      "uploaded_at": "2026-01-18T10:00:00Z"
    }
  ]
}
```

#### `DELETE /documents/{id}`

Dokument löschen (inkl. Vektoren).

**Response:**
```json
{
  "message": "Document deleted",
  "document_id": "doc_123"
}
```

---

### Chat

#### `POST /chats`

Neuen Chat erstellen.

**Request:**
```json
{
  "title": "Forensic Analysis Questions"
}
```

**Response:**
```json
{
  "chat_id": "chat_456",
  "title": "Forensic Analysis Questions",
  "created_at": "2026-01-18T10:15:00Z"
}
```

#### `GET /chats`

Liste aller Chats.

**Response:**
```json
{
  "chats": [
    {
      "id": "chat_456",
      "title": "Forensic Analysis Questions",
      "created_at": "2026-01-18T10:15:00Z",
      "message_count": 5
    }
  ]
}
```

#### `GET /chats/{id}/messages`

Chat-Verlauf abrufen.

**Response:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Was ist digitale Forensik?",
      "timestamp": "2026-01-18T10:16:00Z"
    },
    {
      "role": "assistant",
      "content": "Digitale Forensik ist...",
      "sources": [
        {
          "document": "forensik.pdf",
          "page": 5,
          "relevance": 0.92
        }
      ],
      "timestamp": "2026-01-18T10:16:03Z"
    }
  ]
}
```

---

### Query

#### `POST /query/stream`

RAG-Query mit Streaming-Response.

**Request:**
```json
{
  "query": "Was ist digitale Forensik?",
  "chat_id": "chat_456",
  "options": {
    "top_k": 5,
    "rerank": true,
    "temperature": 0.7
  }
}
```

**Response (SSE):**
```
data: {"type": "sources", "sources": [...]}

data: {"type": "token", "content": "Digitale"}

data: {"type": "token", "content": " Forensik"}

data: {"type": "token", "content": " ist"}

data: {"type": "done"}
```

---

### Zotero

#### `POST /zotero/sync`

Zotero-Bibliothek synchronisieren.

**Response:**
```json
{
  "status": "started",
  "sync_id": "sync_789"
}
```

#### `GET /zotero/status`

Sync-Status prüfen.

**Response:**
```json
{
  "status": "completed",
  "items_synced": 15,
  "items_failed": 0,
  "last_sync": "2026-01-18T09:00:00Z"
}
```

---

## Error Codes

| Code | Bedeutung | Beschreibung |
|------|-----------|--------------|
| 200 | OK | Erfolgreiche Anfrage |
| 201 | Created | Ressource erstellt |
| 400 | Bad Request | Ungültige Parameter |
| 404 | Not Found | Ressource nicht gefunden |
| 500 | Internal Error | Server-Fehler |
| 503 | Service Unavailable | Service nicht erreichbar |

**Error Response:**
```json
{
  "error": "invalid_file_type",
  "message": "Only PDF files are supported",
  "details": {
    "file_type": "application/docx"
  }
}
```

---

## Rate Limits

Aktuell keine Rate Limits implementiert. Für Production:

- **Upload**: 10 Dokumente / Minute
- **Query**: 60 Anfragen / Minute
- **Sync**: 1 Sync / 5 Minuten

---

## Authentication

Aktuell keine Authentication implementiert. Für Production:

```bash
curl -X POST http://localhost:8000/query/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "..."}'
```

---

## Examples

### Kompletter Workflow

```bash
# 1. Dokument hochladen
DOC_ID=$(curl -X POST http://localhost:8000/documents \
  -F "file=@paper.pdf" | jq -r .document_id)

# 2. Warten auf Processing (oder SSE nutzen)
sleep 30

# 3. Chat erstellen
CHAT_ID=$(curl -X POST http://localhost:8000/chats \
  -H "Content-Type: application/json" \
  -d '{"title": "Paper Discussion"}' | jq -r .chat_id)

# 4. Query stellen
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Zusammenfassung?\", \"chat_id\": \"$CHAT_ID\"}"
```

### Python Client

```python
import requests

# Upload
with open('document.pdf', 'rb') as f:
    resp = requests.post(
        'http://localhost:8000/documents',
        files={'file': f}
    )
doc_id = resp.json()['document_id']

# Query
resp = requests.post(
    'http://localhost:8000/query/stream',
    json={
        'query': 'Was ist das Hauptthema?',
        'chat_id': 'chat_123'
    },
    stream=True
)

for line in resp.iter_lines():
    if line:
        print(line.decode())
```
