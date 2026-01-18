# API-Referenz

Übersicht der REST-API für das RAG-System mit Fokus auf die Domänenlogik.

---

## Verfügbare Endpoints

| Service | URL | Beschreibung |
|---------|-----|--------------|
| **Web-Interface** | [http://localhost:3000](http://localhost:3000) | Benutzeroberfläche für Document Upload & Chat |
| **REST-API Dokumentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interaktive OpenAPI (Swagger) Dokumentation |
| **Vector Database UI** | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Qdrant Dashboard für Vektorsuche |

**💡 Hinweis:** Alle API-Endpoints sind detailliert unter [http://localhost:8000/docs#/](http://localhost:8000/docs#/) dokumentiert (wenn die Anwendung läuft).

---

## Domänen-Übersicht

Das RAG-System arbeitet mit **drei Hauptdomänen**:

### 📄 1. Dokumenten-Management

**Workflow:**  
Ein Benutzer lädt ein PDF-Dokument hoch ([`POST /documents`](http://localhost:8000/docs#/Documents/upload_document_documents_post)), welches asynchron verarbeitet wird. Der Fortschritt kann live über einen [Processing-Stream](http://localhost:8000/docs#/Documents/stream_document_processing_documents__document_id__processing_stream_get) verfolgt werden (Server-Sent Events). Nach erfolgreicher Verarbeitung steht das Dokument für semantische Abfragen zur Verfügung.

**Kern-Operationen:**
- **Upload**: Dokument hochladen → Parsing → Chunking → Embedding → Speicherung
- **Monitoring**: Live-Status während der Verarbeitung (Parsing, Chunking, Embedding)
- **Verwaltung**: Liste aller Dokumente abrufen, Dokumente löschen

**Wichtige Endpoints:**
- [`POST /documents`](http://localhost:8000/docs#/Documents/upload_document_documents_post) - PDF hochladen
- [`GET /documents/{id}/processing-stream`](http://localhost:8000/docs#/Documents/stream_document_processing_documents__document_id__processing_stream_get) - Processing live verfolgen (SSE)
- [`GET /documents`](http://localhost:8000/docs#/Documents/list_documents_documents_get) - Alle Dokumente auflisten
- [`DELETE /documents/{id}`](http://localhost:8000/docs#/Documents/delete_document_documents__document_id__delete) - Dokument entfernen

**Technischer Ablauf:**
```
PDF-Upload → Docling-Parsing → Semantische Chunks → mxbai-Embeddings → Qdrant-Speicherung
```

---

### 💬 2. Chat-Sessions

**Workflow:**  
Benutzer erstellen [Chat-Sessions](http://localhost:8000/docs#/Chats/create_chat_chats_post), um einen Kontext für Konversationen aufzubauen. Jede Query wird im Chat-Verlauf gespeichert, sodass das LLM auf frühere Fragen/Antworten referenzieren kann.

**Kern-Operationen:**
- **Session-Management**: Neue Chats erstellen, bestehende auflisten
- **History**: Kompletten Nachrichtenverlauf abrufen
- **Kontextualisierung**: LLM nutzt Chat-History für kohärente Antworten

**Wichtige Endpoints:**
- [`POST /chats`](http://localhost:8000/docs#/Chats/create_chat_chats_post) - Neue Chat-Session starten
- [`GET /chats`](http://localhost:8000/docs#/Chats/list_chats_chats_get) - Alle Chats auflisten
- [`GET /chats/{id}/messages`](http://localhost:8000/docs#/Chats/get_chat_messages_chats__chat_id__messages_get) - Chat-Verlauf abrufen

**Persistenz:**  
Alle Nachrichten werden in PostgreSQL gespeichert.

---

### 🔍 3. RAG-Queries (Retrieval-Augmented Generation)

**Workflow:**  
Eine Benutzeranfrage durchläuft die [RAG-Pipeline](http://localhost:8000/docs#/Query/stream_query_query_stream_post): 
1. **Embedding** der Frage (mxbai-embed-de)
2. **Vector-Search** in Qdrant (semantische Ähnlichkeit)
3. **Reranking** der Top-Ergebnisse (BGE-reranker)
4. **LLM-Generierung** mit relevanten Chunks als Kontext
5. **Streaming** der Antwort Token-für-Token

**Kern-Operationen:**
- **Semantische Suche**: Relevante Dokumenten-Chunks finden
- **Kontext-Anreicherung**: LLM erhält nur relevante Informationen
- **Quellenangaben**: Jede Antwort verweist auf Ursprungsdokumente
- **Streaming**: Progressive Antwort-Generierung (bessere UX)

**Wichtige Endpoints:**
- [`POST /query/stream`](http://localhost:8000/docs#/Query/stream_query_query_stream_post) - RAG-Query mit Streaming-Response (SSE)

**Parameter:**
- `query`: Die Frage/Anfrage
- `chat_id`: Optional - für kontextualisierte Antworten
- `top_k`: Anzahl relevanter Chunks (Standard: 5)
- `rerank`: Reranking aktivieren (empfohlen: true)
- `temperature`: LLM-Kreativität (0.0 = deterministisch, 1.0 = kreativ)

**Response-Format (Server-Sent Events):**
```
data: {"type": "sources", "sources": [...]}  ← Gefundene Quellen
data: {"type": "token", "content": "..."}    ← Token-für-Token Streaming
data: {"type": "done"}                       ← Abschluss
```

---

### 📚 4. Zotero-Integration (Optional)

**Workflow:**  
Synchronisation mit einer [Zotero-Bibliothek](http://localhost:8000/docs#/Zotero/trigger_zotero_sync_zotero_sync_post), um akademische PDFs automatisch zu importieren. PDFs werden wie manuell hochgeladene Dokumente verarbeitet.

**Kern-Operationen:**
- **Sync**: Zotero-Bibliothek mit RAG-System synchronisieren
- **Status**: Überwachung des Sync-Fortschritts

**Wichtige Endpoints:**
- [`POST /zotero/sync`](http://localhost:8000/docs#/Zotero/trigger_zotero_sync_zotero_sync_post) - Synchronisation starten
- [`GET /zotero/status`](http://localhost:8000/docs#/Zotero/get_zotero_status_zotero_status_get) - Sync-Status prüfen

**Konfiguration:**  
Erfordert `.env`-Variablen: `ZOTERO_LIBRARY_ID`, `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_TYPE`

---

## System-Status

**Endpoint:** [`GET /health`](http://localhost:8000/docs#/Health/health_check_health_get)

**Zweck:**  
Prüft die Verfügbarkeit aller kritischen Services (Qdrant, LLM, PostgreSQL).

**Response-Beispiel:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-18T10:30:00Z",
  "services": {
    "qdrant": "connected",
    "llm": "available",
    "postgres": "connected"
  }
}
```

**Verwendung:**  
- Docker Health-Checks
- Monitoring-Systeme
- Load Balancer Health-Checks

---

## Error Handling

**Standard-Fehlercodes:**

| Code | Bedeutung | Beispiel |
|------|-----------|----------|
| 200 | Erfolg | Dokument erfolgreich hochgeladen |
| 400 | Ungültige Anfrage | Falsches Dateiformat (nur PDF erlaubt) |
| 404 | Nicht gefunden | Chat-ID existiert nicht |
| 500 | Server-Fehler | Qdrant nicht erreichbar |
| 503 | Service unavailable | Ollama lädt Modell |

**Error-Response-Format:**
```json
{
  "error": "invalid_file_type",
  "message": "Only PDF files are supported",
  "details": {
    "file_type": "application/docx",
    "allowed_types": ["application/pdf"]
  }
}
```

---

## Typische Workflows

### 📖 Workflow 1: Dokument hochladen und abfragen

```bash
# 1. Dokument hochladen
curl -X POST http://localhost:8000/documents \
  -F "file=@research-paper.pdf"
# → Gibt document_id zurück

# 2. Processing verfolgen (optional)
curl -N http://localhost:8000/documents/{document_id}/processing-stream
# → Live-Updates via SSE

# 3. Chat erstellen
curl -X POST http://localhost:8000/chats \
  -H "Content-Type: application/json" \
  -d '{"title": "Paper Discussion"}'
# → Gibt chat_id zurück

# 4. Frage stellen
curl -N -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Was ist das Hauptergebnis?", "chat_id": "..."}'
# → Streaming-Response mit Quellenangaben
```

### 🔄 Workflow 2: Zotero-Bibliothek synchronisieren

```bash
# 1. Sync starten
curl -X POST http://localhost:8000/zotero/sync

# 2. Status prüfen
curl http://localhost:8000/zotero/status
# → {"status": "completed", "items_synced": 15}

# 3. Dokumente sind jetzt abfragbar
curl http://localhost:8000/documents
```

---

## Best Practices

### ✅ Empfehlungen

- **Streaming nutzen**: `/query/stream` statt blocking requests für bessere UX
- **Reranking aktivieren**: Verbessert Relevanz der Ergebnisse deutlich
- **Chat-IDs nutzen**: Für kontextbewusste Konversationen
- **Health-Check**: Vor wichtigen Operationen System-Status prüfen
- **Error-Handling**: `details`-Feld in Error-Responses nutzen für Debugging

### ⚠️ Limitierungen

- **Dateiformate**: Aktuell nur PDF-Support
- **Parallele Uploads**: Max. 2-3 gleichzeitig (Performance)
- **Query-Länge**: Max. 1000 Zeichen
- **Rate Limiting**: Noch nicht implementiert (geplant für Production)

---

## Weiterführende Dokumentation

- **[OpenAPI Docs (Live)](http://localhost:8000/docs)** - Interaktive API-Exploration mit Try-it-out
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - RAG-Pipeline im Detail
- **[TECHNOLOGIES.md](./TECHNOLOGIES.md)** - Embedding-Models, LLMs, Qdrant
- **[DEVELOPMENT.md](./DEVELOPMENT.md)** - API-Entwicklung & Testing

---

## Beispiel-Integration (Python)

```python
import requests
import json

class RAGClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def upload_document(self, pdf_path):
        """Dokument hochladen"""
        with open(pdf_path, 'rb') as f:
            response = requests.post(
                f"{self.base_url}/documents",
                files={'file': f}
            )
        return response.json()['document_id']
    
    def create_chat(self, title):
        """Chat-Session erstellen"""
        response = requests.post(
            f"{self.base_url}/chats",
            json={'title': title}
        )
        return response.json()['chat_id']
    
    def query(self, question, chat_id=None):
        """RAG-Query mit Streaming"""
        response = requests.post(
            f"{self.base_url}/query/stream",
            json={'query': question, 'chat_id': chat_id},
            stream=True
        )
        
        for line in response.iter_lines():
            if line:
                data = line.decode('utf-8').replace('data: ', '')
                yield json.loads(data)

# Verwendung
client = RAGClient()
doc_id = client.upload_document('paper.pdf')
chat_id = client.create_chat('Paper Analysis')

for event in client.query('Was ist das Hauptthema?', chat_id):
    if event['type'] == 'token':
        print(event['content'], end='', flush=True)
```
