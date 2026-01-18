# Performance-Optimierung

## Docker Memory-Limits erhöhen
**Dokumentation:** [Microsoft WSL Config Guide](https://learn.microsoft.com/en-us/windows/wsl/wsl-config#configure-global-options-with-wslconfig)

### Windows (Native Docker in WSL 2)
**Memory wird in WSL 2 konfiguriert:**
1. **Windows-Taste drücken**
2. **WSL Settings eingeben**
3. **Konfiguration anpassen**
4. **"Apply & Restart" klicken**

### macOS (Docker Desktop)
**Memory wird direkt in Docker Desktop App verwaltet:**
1. **Docker Desktop öffnen**
2. **Settings → Resources → Memory**
3. **Memory-Slider auf 12GB+ erhöhen**
4. **"Apply & Restart" klicken**


### Linux (Native Docker)
**Memory wird vom Host-System verwaltet** - Docker nutzt automatisch verfügbaren RAM.
```bash
free -h # ram check
```
-

## Performance-Tuning
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
    shm_size: '2gb'
```

**3. CPU-Affinity setzen:**
```yaml
services:
  qdrant:
    cpus: 2.0 
```


### Container Build-Zeit reduzieren

**Problem:** Backend braucht 2+ Minuten zum Start

**Lösung:**
- HuggingFace-Models in Volume cachen (siehe docker-compose.yml)
- Model-Download im Dockerfile statt zur Laufzeit


### Langsame Embedding-Generierung

**Problem:** Dokument-Upload dauert 5+ Minuten

**Lösungen:**
1. **GPU aktivieren** (ollama bietet native Umsetzung für NVIDIA/AMD GPUs)
2. **Batch-Size erhöhen** in `backend/core/embeddings.py`:
   ```python
   # Statt 32
   batch_size = 64  # wenn genug RAM/GPU vorhanden
   ```
3. **Kleinere Chunks** in `.env`:
   ```bash
   # Statt 500
   CHUNK_SIZE=300
   ```
