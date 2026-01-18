# Performance-Optimierung

Anleitungen zur Performance-Optimierung des RAG-Systems auf verschiedenen Betriebssystemen.

---

## Docker Memory-Limits erhöhen

### Windows (Docker Desktop + WSL 2)

**Wichtig:** Bei WSL 2 wird der Memory automatisch von Windows verwaltet. Sie haben zwei Optionen:

#### Option 1: Docker Desktop Settings (einfach)
```
Docker Desktop → Settings → Resources → Memory: 12GB+
```

#### Option 2: WSL Memory-Limit erhöhen (mehr Kontrolle)

Windows verwaltet WSL 2 Memory dynamisch. Für feste Limits:

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

### macOS (Docker Desktop)

**Memory wird direkt in Docker Desktop App verwaltet:**

1. **Docker Desktop öffnen**
2. **Settings → Resources → Memory**
3. **Memory-Slider auf 12GB+ erhöhen**
4. **"Apply & Restart" klicken**

**Empfohlene Einstellungen:**
- **Memory**: 12-16GB (für lokale LLMs)
- **CPUs**: 6-8 Cores
- **Swap**: 2-4GB
- **Disk**: 50GB+

**Alternative: CLI-Konfiguration**

Bearbeiten Sie `~/Library/Group Containers/group.com.docker/settings.json`:
```json
{
  "memoryMiB": 12288,
  "cpus": 6,
  "swapMiB": 4096
}
```

Dann Docker Desktop neu starten.

---

### Linux (Native Docker)

**Memory wird vom Host-System verwaltet** - Docker nutzt automatisch verfügbaren RAM.
**In docker-compose.yml:**
```yaml
services:
  backend:
    # ...existing config...
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

**System-RAM prüfen:**
```bash
free -h
```

**Docker-Resource-Usage überwachen:**
```bash
docker stats
```

---

## Systemressourcen-Empfehlungen

### Minimal-Setup (Cloud-LLM)

Für Betrieb mit Anthropic/OpenAI (kein lokales LLM):

| Ressource | Minimum | Empfohlen |
|-----------|---------|-----------|
| **RAM** | 4GB | 8GB |
| **CPU** | 2 Cores | 4 Cores |
| **Disk** | 10GB | 20GB |
| **GPU** | Nicht benötigt | - |

### Standard-Setup (Ollama lokal)

Für Betrieb mit lokalem Ollama LLM:

| Ressource | Minimum | Empfohlen |
|-----------|---------|-----------|
| **RAM** | 8GB | 16GB |
| **CPU** | 4 Cores | 6-8 Cores |
| **Disk** | 20GB | 50GB |
| **GPU** | Optional | NVIDIA 6GB+ VRAM |

### High-Performance Setup

Für optimale Performance mit GPU-Acceleration:

| Ressource | Empfohlen |
|-----------|-----------|
| **RAM** | 32GB |
| **CPU** | 8-12 Cores |
| **Disk** | 100GB SSD |
| **GPU** | NVIDIA RTX 3060+ (12GB VRAM) |

---

## Performance-Tuning

### Docker-Compose-Optimierungen

**1. Build-Cache aktivieren:**
```yaml
services:
  backend:
    build:
      context: ./backend
      cache_from:
        - backend:latest
```

**2. Shared Memory erhöhen (für ML-Workloads):**
```yaml
services:
  backend:
    shm_size: '2gb'  # Wichtig für HuggingFace-Modelle
```

**3. CPU-Affinity setzen:**
```yaml
services:
  qdrant:
    cpus: 2.0  # Dedizierte CPU-Cores für Qdrant
```

### Environment-Variable Optimierungen

**In `.env` hinzufügen:**

```bash
# HuggingFace Model-Cache (beschleunigt Restarts)
HF_HOME=/app/models/transformers

# PyTorch Performance
TORCH_COMPILE=1
TORCH_CUDNN_V8_API_ENABLED=1

# Qdrant Performance
QDRANT_HNSW_EF_CONSTRUCT=100
QDRANT_HNSW_M=16

# Docling Parallelisierung
DOCLING_WORKERS=4
```

### Ollama GPU-Optimierung

**Für NVIDIA GPUs:**

```yaml
services:
  ollama:
    environment:
      - OLLAMA_NUM_PARALLEL=2        # Parallele Requests
      - OLLAMA_MAX_LOADED_MODELS=2   # Gleichzeitig geladene Modelle
      - OLLAMA_GPU_LAYERS=35         # GPU-Layer (mehr = schneller)
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

**VRAM-Management:**

| GPU VRAM | Empfohlenes Modell | GPU Layers |
|----------|-------------------|------------|
| 6GB | phi3:mini | 35 |
| 8GB | llama2:7b | 35 |
| 12GB | mistral:7b | 40 |
| 16GB+ | llama2:13b | 45 |

---

## Monitoring

### Resource-Usage überwachen

**Alle Container:**
```bash
docker stats
```

**Spezifischer Container:**
```bash
docker stats backend
```

**Logs mit Resource-Info:**
```bash
docker-compose logs -f --tail=100 backend
```

### Performance-Metriken

**Document Processing:**
```bash
# Zeit messen
time curl -X POST http://localhost:8000/documents \
  -F "file=@test.pdf"
```

**Query Performance:**
```bash
# Mit Zeitstempel
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "Test?"}' \
  --trace-time
```

---

## Troubleshooting Performance

### Container startet langsam

**Problem:** Backend braucht 2+ Minuten zum Start

**Lösung:**
- HuggingFace-Models in Volume cachen (siehe docker-compose.yml)
- Model-Download im Dockerfile statt zur Laufzeit

### Hoher Memory-Verbrauch

**Problem:** Docker nutzt >16GB RAM

**Diagnose:**
```bash
docker system df -v
docker stats --no-stream
```

**Lösungen:**
- Ungenutzte Container stoppen: `docker-compose stop <service>`
- Build-Cache leeren: `docker builder prune`
- Volumes aufräumen: `docker volume prune`

### Langsame Embedding-Generierung

**Problem:** Dokument-Upload dauert 5+ Minuten

**Lösungen:**
1. **GPU aktivieren** (siehe SETUP.md)
2. **Batch-Size erhöhen** in `backend/core/embeddings.py`:
   ```python
   batch_size = 32  # Standard
   batch_size = 64  # Schneller (mehr RAM)
   ```
3. **Kleinere Chunks** in `.env`:
   ```bash
   CHUNK_SIZE=300  # Statt 500
   ```

### Qdrant Queries langsam

**Problem:** Vector-Search braucht >2 Sekunden

**Lösungen:**
1. **HNSW-Parameter tunen** in Qdrant-Collection:
   ```python
   hnsw_config = {
       "m": 16,           # Mehr = schneller, mehr RAM
       "ef_construct": 100
   }
   ```
2. **Index aufwärmen**:
   ```bash
   curl -X POST http://localhost:6333/collections/documents/points/search \
     -H "Content-Type: application/json" \
     -d '{"vector": [0.1, ...], "limit": 10}'
   ```

---

## Benchmarks

**Typische Performance (MacBook Pro M2, 16GB RAM):**

| Operation | Dauer | Notizen |
|-----------|-------|---------|
| Container-Start | 30-60s | Mit Model-Cache |
| PDF-Upload (10MB) | 90-120s | Docling + Embedding |
| Vector-Search | 50-200ms | 1000 Dokumente |
| RAG-Query | 3-8s | Mit Streaming |
| LLM-Generation | 20-50 tokens/s | Ollama llama2:7b |

**Mit NVIDIA RTX 3080 (10GB):**

| Operation | Dauer | Speedup |
|-----------|-------|---------|
| PDF-Upload | 45-60s | ~2x |
| LLM-Generation | 80-120 tokens/s | ~3x |

---

## Best Practices

### ✅ Do's

- **Use Cloud-LLMs** für Development (schneller, kein GPU nötig)
- **Cache HuggingFace Models** in Docker Volumes
- **Monitor Resource-Usage** regelmäßig
- **Update Docker** auf neueste Version
- **Use SSD** für Docker-Volumes (nicht HDD)

### ❌ Don'ts

- **Zu viele parallele Uploads** (max 2-3 gleichzeitig)
- **Zu kleine Memory-Limits** (<8GB für lokale LLMs)
- **Models im Container** statt in Volumes
- **Debug-Logging** in Production (performance-hit)
- **Swap auf HDD** (sehr langsam)

---

## Weitere Optimierungen

### Production-Ready

Für Production-Deployment siehe:
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - Kubernetes, Load Balancing
- **[MONITORING.md](./MONITORING.md)** - Prometheus, Grafana
- **[SCALING.md](./SCALING.md)** - Horizontal Scaling

### Hardware-Upgrade Empfehlungen

**Priorisierung:**
1. **RAM** (16GB → 32GB) - Größter Impact
2. **SSD** (HDD → NVMe SSD) - 5x schneller
3. **GPU** (CPU → NVIDIA) - 3x schneller für LLM
4. **CPU** (4 → 8 Cores) - Parallelisierung
