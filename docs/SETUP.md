# Setup & Installation

Komplette Anleitung zur Installation und Konfiguration des RAG-Systems.

## Systemanforderungen
- **Docker-Desktop** installiert (https://docs.docker.com/compose/install)
- **Mindestens 8 GB RAM** (12 GB empfohlen für lokale LLMs)

## Quick Start
**1. Repository klonen:**
```bash
git clone https://github.com/DuncanSARapp/sma-rag-python.git && cd sma-rag-python
```

**2. Services starten:**
```bash
docker-compose up -d --build
```

## Konfiguration

### Minimal-Setup (Local)
**Wird automatisch genutzt, wenn keine env-Variablen gesetzt sind:**
```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=llama2
```

### Provider-Setup (Cloud)
```dotenv
LLM_PROVIDER=anthropic 
LLM_MODEL=claude-sonnet-4 
ANTHROPIC_API_KEY=sk-ant-...
```
oder

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
OPENAI_API_KEY=sk-...
```

### Zotero-Integration (Optional)
Für automatischen Sync mit Zotero-Bibliothek:
```dotenv
ZOTERO_LIBRARY_ID=12345678
ZOTERO_API_KEY=your-api-key
ZOTERO_LIBRARY_TYPE=user
```

### Erweiterte Einstellungen
Siehe [`.env.example`](../.env.example) für:
- Chunking-Parameter
- Sucheinstellungen
- Modell-Konfigurationen
- Performance-Anpassungen
---

## Troubleshooting

### Container/Service startet nicht?
```bash
docker-compose logs <CONTAINER> -f 
```

### Ollama-Modelle nicht im Container enthalten?
```bash
# Nachträglich LLM-Modelle in Ollama laden
docker exec -it ollama ollama pull llama2
docker exec -it ollama ollama list
```
### Speicherprobleme (SIGKILL: Out of Memory)
- **LLM anpassen:** Leichtere Modelle wie `phi3:mini` nutzen
- **Docker-Ressourcen erhöhen:** Siehe [PERFORMANCE.md](./PERFORMANCE.md)
