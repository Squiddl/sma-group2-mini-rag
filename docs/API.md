# API-Referenz
Übersicht der REST-API für das RAG-System mit Fokus auf die Domänenlogik.

## User-Interfaces
---

| Service                    | URL                                                                | Beschreibung                                  |
|----------------------------|--------------------------------------------------------------------|-----------------------------------------------|
| **Web-Interface**          | [http://localhost:3000](http://localhost:3000)                     | Benutzeroberfläche für Document Upload & Chat |
| **REST-API Dokumentation** | [http://localhost:8000/docs](http://localhost:8000/docs)           | Interaktive OpenAPI (Swagger) Dokumentation   |
| **Vector Database UI**     | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Qdrant Dashboard für Vektorsuche              |

---

## Domänen-Übersicht

Das RAG-System arbeitet mit **drei Hauptdomänen**:

### 📄 1. Dokumenten-Management

**Workflow:**  
Ein Benutzer lädt ein PDF-Dokument hoch ([`POST /documents`](http://localhost:8000/docs#/Documents/upload_document_documents_post)), welches asynchron verarbeitet wird. Der Fortschritt kann live über einen [Processing-Stream](http://localhost:8000/docs#/Documents/stream_document_processing_documents__document_id__processing_stream_get) verfolgt werden (Server-Sent Events). Nach erfolgreicher Verarbeitung steht das Dokument für semantische Abfragen zur Verfügung.

**Wichtige Endpoints:**
- [`POST /documents`](http://localhost:8000/docs#/Documents/upload_document_documents_post) - PDF hochladen
- [`GET /documents/{id}/processing-stream`](http://localhost:8000/docs#/Documents/stream_document_processing_documents__document_id__processing_stream_get) - Processing live verfolgen (SSE)
- [`GET /documents`](http://localhost:8000/docs#/Documents/list_documents_documents_get) - Alle Dokumente auflisten
- [`DELETE /documents/{id}`](http://localhost:8000/docs#/Documents/delete_document_documents__document_id__delete) - Dokument entfernen
---

### 💬 2. Chat-Sessions

**Workflow:**  
Benutzer erstellen [Chat-Sessions](http://localhost:8000/docs#/Chats/create_chat_chats_post), um einen Kontext für Konversationen aufzubauen. 
Jede Query wird im Chat-Verlauf gespeichert, sodass das LLM auf frühere Fragen/Antworten referenzieren kann.Alle Nachrichten werden in PostgreSQL gespeichert.

**Wichtige Endpoints:**
- [`POST /chats`](http://localhost:8000/docs#/Chats/create_chat_chats_post) - Neue Chat-Session starten
- [`GET /chats`](http://localhost:8000/docs#/Chats/list_chats_chats_get) - Alle Chats auflisten
- [`GET /chats/{id}/messages`](http://localhost:8000/docs#/Chats/get_chat_messages_chats__chat_id__messages_get) - Chat-Verlauf abrufen
---

### 🔍 3. RAG-Queries (Retrieval-Augmented Generation)

**Workflow:**  
Eine Benutzeranfrage durchläuft die [RAG-Pipeline](http://localhost:8000/docs#/Query/stream_query_query_stream_post): 
1. **Embedding** der Frage (mxbai-embed-de)
2. **Vector-Search** in Qdrant (semantische Ähnlichkeit)
3. **Reranking** der Top-Ergebnisse (BGE-reranker)
4. **LLM-Generierung** mit relevanten Chunks als Kontext
5. **Streaming** der Antwort Token-für-Token

**Wichtige Endpoints:**
- [`POST /query/stream`](http://localhost:8000/docs#/Query/stream_query_query_stream_post) - RAG-Query mit Streaming-Response (SSE)

**Parameter:**
- `query`: Die Frage/Anfrage
- `chat_id`: Optional - für kontextualisierte Antworten
- `top_k`: Anzahl relevanter Chunks (Standard: 5)
- `rerank`: Reranking aktivieren (empfohlen: true)
- `temperature`: LLM-Kreativität (0.0 = deterministisch, 1.0 = kreativ)
---

### 📚 4. Zotero-Integration

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
