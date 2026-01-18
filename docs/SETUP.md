# Setup & Installation

Komplette Anleitung zur Installation und Konfiguration des RAG-Systems.

---

## Systemanforderungen

- **Docker** mit Docker Compose
- **Mindestens 8 GB RAM** (12 GB empfohlen für lokale LLMs)
- **Windows**: WSL 2 (empfohlen für beste Performance)
- Optional: NVIDIA GPU mit CUDA-Support für schnellere Inferenz

### Windows-spezifisch

**WSL-Version prüfen:**
```powershell
wsl --status
```

**🎯 Entscheidungs-Guide für Windows:**

| Nutzungsszenario | Empfehlung |
|------------------|------------|
| Development, Testing | ✅ **Docker Desktop** |
| GPU mit Ollama (lokal) | ✅ **Docker Desktop** (GPU-Support seit 2023 integriert) |
| Headless Server, CI/CD | 🔧 WSL-Native Docker |
| Maximale Performance | 🔧 WSL-Native + systemd |

**Für 95% der User:** Docker Desktop ist die beste Wahl.

**Wichtig:** Docker Desktop nutzt bereits WSL 2 als Backend - Sie bekommen WSL-Performance automatisch!

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

**Windows:** Docker Desktop nutzt WSL 2 - Memory wird automatisch von Windows verwaltet.  
**macOS:** Memory-Limit direkt in Docker Desktop App erhöhen (Settings → Resources → Memory: 12GB+).  
**Linux:** Docker nutzt automatisch verfügbaren Host-RAM.

➡️ **Detaillierte Anleitungen:** Siehe [PERFORMANCE.md](./PERFORMANCE.md)

---

## GPU-Support (NVIDIA)

### Docker Desktop GPU-Support (Windows/macOS)

**Für Windows/macOS ist Docker Desktop empfohlen:**

**1. NVIDIA Driver installieren:**
- **Windows:** [NVIDIA Driver Download](https://www.nvidia.com/Download/index.aspx) (Min. 470.76+)
- **macOS:** Keine NVIDIA GPU-Unterstützung (Metal für Apple Silicon)

**2. GPU in Docker Desktop aktivieren:**
```
Docker Desktop → Settings → Resources → Enable GPU
```

**3. GPU testen:**
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**4. GPU in docker-compose.yml aktivieren:**
```yaml
services:
  ollama:
    # ...existing config...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

➡️ **Erweiterte GPU-Optimierung:** Siehe [PERFORMANCE.md](./PERFORMANCE.md)

---

## WSL-Distribution wählen (Windows)

**Für Docker Desktop:** Ubuntu 22.04 LTS empfohlen

| Distribution | Empfehlung | Begründung |
|--------------|------------|------------|
| **Ubuntu 22.04 LTS** | ⭐⭐⭐⭐⭐ | Best Practice, LTS bis 2027 |
| **Ubuntu 24.04 LTS** | ⭐⭐⭐⭐ | Neueste Packages, LTS bis 2029 |
| **Debian 12** | ⭐⭐⭐ | Minimal, stabil |

**Installation:**
```powershell
wsl --install Ubuntu-22.04
wsl --set-default Ubuntu-22.04
```


## Deinstallation

```bash
docker-compose down -v && docker-compose down --rmi all
```
