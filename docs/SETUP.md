# Setup & Installation

Komplette Anleitung zur Installation und Konfiguration des RAG-Systems.

---

## Systemanforderungen

- **Docker** 20.10+ mit Docker Compose
- **Mindestens 8 GB RAM** (12 GB empfohlen für lokale LLMs)
- **10 GB freier Speicherplatz**
- Optional: NVIDIA GPU mit CUDA-Support für schnellere Inferenz

---

## Quick Start

**1. Repository klonen:**
```bash
git clone https://github.com/DuncanSARapp/academic-rag-python.git
cd academic-rag-python
```

**2. Umgebungsvariablen konfigurieren:**
```bash
cp .env.example .env
# .env nach Bedarf anpassen
```

**3. Services starten:**
```bash
docker-compose up -d --build
```

**4. Logs ansehen (optional):**
```bash
docker-compose logs -f
```

**Verfügbare Endpoints:**

| Service | URL                        | Beschreibung |
|---------|----------------------------|--------------|
| Frontend | http://localhost:3000     | Web-Interface |
| API Docs | http://localhost:8000/docs | OpenAPI-Dokumentation |
| Qdrant UI | http://localhost:6333/dashboard | Vector DB Interface |

---

## Konfiguration

### Minimal-Setup (Standard)

Funktioniert out-of-the-box mit lokalem Ollama:

```bash
# .env
LLM_PROVIDER=ollama
LLM_MODEL=llama2
```

### Cloud-Provider (Bessere Qualität)

Für bessere Ergebnisse mit Cloud-APIs:

```bash
# Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Oder OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Zotero-Integration (Optional)

Für automatischen Sync mit Zotero-Bibliothek:

```bash
ZOTERO_LIBRARY_ID=12345678
ZOTERO_API_KEY=your-api-key
ZOTERO_LIBRARY_TYPE=user
```

### Erweiterte Einstellungen

Siehe [`.env.example`](../.env.example) für:
- Chunking-Parameter
- Sucheinstellungen
- Modell-Konfigurationen
- Performance-Tuning

---

## Troubleshooting

### Services starten nicht

```bash
# Logs prüfen
docker-compose logs backend
docker-compose logs qdrant

# Services neu starten
docker-compose down
docker-compose up -d --build
```

### Ollama-Modelle fehlen

```bash
# In Ollama-Container
docker exec -it ollama ollama pull llama2
docker exec -it ollama ollama list
```

### Speicherprobleme

```bash
# Docker-Ressourcen erhöhen (Docker Desktop)
# Settings → Resources → Memory: 8GB+
```

---

## Deinstallation

```bash
# Services stoppen und Volumes löschen
docker-compose down -v

# Images entfernen
docker-compose down --rmi all
```
