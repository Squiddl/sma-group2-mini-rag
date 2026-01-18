# Setup & Installation

Komplette Anleitung zur Installation und Konfiguration des RAG-Systems.

---

## Systemanforderungen

- **Docker** 20.10+ mit Docker Compose
- **Mindestens 8 GB RAM** (12 GB empfohlen für lokale LLMs)
- **10 GB freier Speicherplatz**
- **Windows**: WSL 2 (empfohlen für beste Performance)
- Optional: NVIDIA GPU mit CUDA-Support für schnellere Inferenz

### Windows-spezifisch

**WSL-Version prüfen:**
```powershell
wsl --status
```

**Empfehlung:** WSL 2 mit Debian/Ubuntu für optimale Docker- und GPU-Performance

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

Siehe Abschnitt [Performance-Optimierung (Windows)](#performance-optimierung-windows) unten.

---

## Performance-Optimierung (Windows)

### Docker Desktop Memory erhöhen

**Option 1: Docker Desktop Settings (einfach)**
```
Docker Desktop → Settings → Resources → Memory: 12GB+
```

**Option 2: WSL Memory-Limit erhöhen (empfohlen für mehr Kontrolle)**

1. **WSL-Version prüfen:**
```powershell
wsl --status
```

2. **Globale WSL-Konfiguration erstellen:**
```powershell
notepad $env:USERPROFILE\.wslconfig
```

3. **Konfiguration hinzufügen:**
```ini
[wsl2]
memory=12GB          # Maximal verfügbarer RAM für WSL
processors=6         # CPU-Kerne für WSL
swap=4GB             # Swap-Speicher
localhostForwarding=true
```

4. **WSL neu starten:**
```powershell
wsl --shutdown
```

5. **Überprüfung:**
```bash
# In WSL
free -h
nproc
```

**Dokumentation:** [Microsoft WSL Config Guide](https://learn.microsoft.com/en-us/windows/wsl/wsl-config#configure-global-options-with-wslconfig)

---

## GPU-Support (NVIDIA)

### WSL 2 vs. Docker Desktop für GPU

| Aspekt | WSL 2 (Debian/Ubuntu) | Docker Desktop |
|--------|----------------------|----------------|
| **GPU-Support** | ✅ Native CUDA | ✅ Via WSL Backend |
| **Performance** | ⚡⚡⚡ Optimal | ⚡⚡ Gut |
| **Setup-Komplexität** | Medium | Einfach |
| **Empfohlen für** | Production, GPU-intensive Workloads | Development, Quick Start |

### GPU-Setup (NVIDIA + WSL 2)

**1. NVIDIA Driver installieren (Windows-Host):**
- [NVIDIA Driver Download](https://www.nvidia.com/Download/index.aspx)
- Mindestens Version 470.76+

**2. CUDA in WSL prüfen:**
```bash
nvidia-smi
```

**3. Docker mit GPU-Support:**
```bash
# NVIDIA Container Toolkit (in WSL)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
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

**5. Testen:**
```bash
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### WSL-Distribution wählen

**Debian vs. Ubuntu für Container + GPU:**

| Distribution | Vorteile | Nachteile |
|--------------|----------|-----------|
| **Debian** | Stabil, minimal, weniger Overhead | Ältere Pakete |
| **Ubuntu** | Aktuellere Pakete, bessere NVIDIA-Support | Mehr Bloat |

**Empfehlung:** Ubuntu 22.04 LTS für beste NVIDIA/CUDA-Kompatibilität

**Installation:**
```powershell
wsl --install Ubuntu-22.04
wsl --set-default Ubuntu-22.04
```

---

## Deinstallation

```bash
# Services stoppen und Volumes löschen
docker-compose down -v

# Images entfernen
docker-compose down --rmi all
```
